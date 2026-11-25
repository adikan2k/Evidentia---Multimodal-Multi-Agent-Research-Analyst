"""The real-world audit (D-042): ask AI tools the fixed questions, audit every answer, summarise.

    uv run python -m evals realworld questions                     # free, done once
    uv run python -m evals realworld run --set pilot --cap 3       # paid; ask first
    uv run python -m evals realworld summary --set pilot           # free
    uv run python -m evals realworld reask --cap 5                 # paid; ask first (D-043, 1c)
    uv run python -m evals realworld reask-summary                 # free
    uv run python -m evals realworld reread --cap 1                # paid; ask first (D-046)
    uv run python -m evals realworld reread-summary                # free
    uv run python -m evals realworld short --cap 0.6               # paid; ask first (D-047)
    uv run python -m evals realworld short-summary                 # free

Every answer and every audit is saved, so a rerun only pays for what is missing. Each answer is
audited twice: with the page judge as shipped (Haiku) and with OpenAI's gpt-6-luna as the page
judge, to see whether a Claude judge treats Claude's answers differently.
"""

import argparse
import asyncio
import json
import random
import re
import statistics
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from evals.aggrefact import RowLedger
from evals.common import ROOT, read_jsonl, write_result
from evals.realworld_questions import QUESTIONS, write_questions
from evals.stats import RESAMPLES, SEED
from evidentia.audit.answers import answer_with_web_search, claude_answer_with_web_search
from evidentia.audit.events import AuditEventBuilder
from evidentia.audit.graph import AuditDeps, run_audit
from evidentia.config import Settings, load_settings
from evidentia.cost import BudgetExceeded, Ledger
from evidentia.embed import Embedder
from evidentia.events import host_of
from evidentia.fetch import Fetcher
from evidentia.llm import LLM
from evidentia.tracing import LangfuseTracer, Tracer

HERE = ROOT / "realworld"
TOOLS = ("openai", "claude")
JUDGES = {"haiku": "claude-haiku-5-5", "luna": "gpt-6-luna"}  # page judge, as shipped / check
TOPICS = ("science", "health", "technology", "economy", "sport_culture")
# Fixed in D-042 before any answer: Natural Questions 1 to 5, and question 1 of each topic.
PILOT = [f"nq-{n:02d}" for n in range(1, 6)] + [f"{t}-01" for t in TOPICS]
CONCURRENT_QUESTIONS = 3
FAILED = {"not_found", "contradicted"}
VERDICT = FAILED | {"supported", "partial"}
# The re-ask run (D-043, phase 1c). All four numbers were fixed before any repeated answer.
REASK = HERE / "reask"
REASK_SEED = 20261202
REASK_PER_SOURCE = 10
REPEATS = 3
SEARCH_CAP = 5  # the cap Claude's search tool already ran under (`max_uses`)


def load_questions(which: str) -> list[dict]:
    rows = read_jsonl(QUESTIONS)
    if which == "pilot":
        return [q for q in rows if q["id"] in PILOT]
    return rows


def answer_path(tool: str, qid: str, root: Path = HERE) -> Path:
    return root / "answers" / tool / f"{qid}.json"


def audit_path(judge: str, tool: str, qid: str, root: Path = HERE) -> Path:
    return root / "audits" / judge / tool / f"{qid}.json"


def choose_reask(questions: list[dict]) -> list[dict]:
    """The questions asked again: the same number from each source, by a fixed seed."""
    rng = random.Random(REASK_SEED)
    chosen: list[dict] = []
    for source in sorted({q["source"] for q in questions}):
        group = sorted((q for q in questions if q["source"] == source), key=lambda q: q["id"])
        chosen += rng.sample(group, min(REASK_PER_SOURCE, len(group)))
    return sorted(chosen, key=lambda q: q["id"])


def reask_items(questions: list[dict]) -> list[dict]:
    """One item per repeat. `of` names the question, so repeats can be set side by side."""
    return [
        q | {"id": f"{q['id']}-r{n}", "of": q["id"], "repeat": n}
        for q in choose_reask(questions)
        for n in range(1, REPEATS + 1)
    ]


def save(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# Running.


class Runner:
    def __init__(
        self,
        settings: Settings,
        cap: float,
        tracer: Tracer,
        root: Path = HERE,
        judges: tuple[str, ...] = tuple(JUDGES),
        max_searches: int | None = None,
    ) -> None:
        self.s = settings
        self.tracer = tracer
        self.root = root
        self.judges = judges
        self.max_searches = max_searches  # OpenAI only; Claude's tool carries its own cap
        self.shared = Ledger(cap)
        # One fetcher for every audit, so the wait between requests to one site holds across all.
        self.fetcher = Fetcher(settings, tracer)
        self.voyage = Embedder(settings, self.shared, tracer).client
        self.gate = asyncio.Semaphore(CONCURRENT_QUESTIONS)

    async def answer(self, tool: str, q: dict) -> dict:
        path = answer_path(tool, q["id"], self.root)
        saved = load(path)
        if saved is not None:
            return saved
        ledger = RowLedger(self.shared)
        if tool == "openai":
            got = await answer_with_web_search(
                q["question"], self.s, ledger, max_searches=self.max_searches
            )
        else:
            got = await claude_answer_with_web_search(q["question"], self.s, ledger, self.tracer)
        body = {"id": q["id"], "tool": tool} | got
        save(path, body)
        return body

    async def audit(self, tool: str, judge: str, q: dict, answer: dict) -> None:
        path = audit_path(judge, tool, q["id"], self.root)
        if path.exists():
            return
        settings = self.s.model_copy(update={"page_judge_model": JUDGES[judge]})
        ledger = RowLedger(self.shared)
        deps = AuditDeps(
            settings=settings,
            ledger=ledger,
            tracer=self.tracer,
            llm=LLM(settings, ledger),
            fetcher=self.fetcher,
            embedder=Embedder(settings, ledger, self.tracer, client=self.voyage),
        )
        builder = AuditEventBuilder(ledger)
        state = await run_audit(answer["text"], deps, lambda node, update: None)
        report = builder.report(state)
        save(path, {"id": q["id"], "tool": tool, "judge": JUDGES[judge], "report": report})

    async def one(self, q: dict, tools: list[str]) -> None:
        async with self.gate:
            for tool in tools:
                try:
                    answer = await self.answer(tool, q)
                    for judge in self.judges:
                        await self.audit(tool, judge, q, answer)
                    print(f"  {q['id']} {tool}: done")
                except BudgetExceeded:
                    raise
                except Exception as err:  # saved work stays; a rerun tries the rest again
                    print(f"  {q['id']} {tool}: {type(err).__name__}: {str(err)[:120]}")

    async def run(self, questions: list[dict], tools: list[str]) -> None:
        try:
            async with asyncio.TaskGroup() as group:
                for q in questions:
                    group.create_task(self.one(q, tools))
        except* BudgetExceeded as errors:
            print(f"  stopped at the cap: {errors.exceptions[0]}")
        finally:
            await self.fetcher.aclose()
        print(f"  spent ${self.shared.spent:.4f} this command")


# Summarising.


def counts(report: dict) -> dict[str, int]:
    labels = Counter(c["label"] for c in report["claims"])
    card = report["scorecard"]
    # D-042, after the pilot: the headline counts only claims whose own sentence carries a
    # citation. A claim that takes its paragraph's closing citation is reported apart.
    own = Counter(c["label"] for c in report["claims"] if c.get("cited_by") == "sentence")
    para = Counter(c["label"] for c in report["claims"] if c.get("cited_by") == "paragraph")
    return {
        "verdict_own": sum(own[label] for label in VERDICT),
        "failed_own": sum(own[label] for label in FAILED),
        "verdict_paragraph": sum(para[label] for label in VERDICT),
        "failed_paragraph": sum(para[label] for label in FAILED),
        # For the bounds (D-043): own-cited claims left without a verdict.
        "unread_own": own["unchecked"],
        "needs_human_own": own["needs_human"],
        "supported": labels["supported"],
        "not_found": labels["not_found"],
        "claims": len(report["claims"]),
        "with_verdict": sum(labels[label] for label in VERDICT),
        "failed": sum(labels[label] for label in FAILED),
        "contradicted": labels["contradicted"],
        "partial": labels["partial"],
        "needs_human": labels["needs_human"],
        "unchecked": labels["unchecked"],
        "dead_link": labels["dead_link"],
        "uncited": labels["uncited"],
        "citation_unread": labels["citation_unread"],
        "pages_cited": card["pages_cited"],
        "pages_read": card["pages_read"],
        "audit_usd": card["usd"],
    }


def ratio(rows: list[dict], top: str, bottom: str) -> float | None:
    den = sum(r[bottom] for r in rows)
    return sum(r[top] for r in rows) / den if den else None


def interval(rows: list[dict], stat: Callable[[list[dict]], float | None]) -> dict:
    """The statistic over questions, with a 95% bootstrap interval that resamples questions."""
    rng = random.Random(SEED)
    boot = sorted(
        v
        for v in (stat([rows[rng.randrange(len(rows))] for _ in rows]) for _ in range(RESAMPLES))
        if v is not None
    )
    value = stat(rows)
    rnd = lambda v: None if v is None else round(v, 4)  # noqa: E731
    if not boot:
        return {"value": rnd(value), "ci_low": None, "ci_high": None}
    lo, hi = boot[int(0.025 * len(boot))], boot[int(0.975 * len(boot)) - 1]
    return {"value": rnd(value), "ci_low": rnd(lo), "ci_high": rnd(hi)}


ALL_LABELS = (
    "supported",
    "partial",
    "contradicted",
    "not_found",
    "needs_human",
    "unchecked",
    "dead_link",
    "citation_unread",
    "uncited",
)


def bounds(rows: list[dict], undecided: tuple[str, ...]) -> dict[str, Any]:
    """The headline if every own-cited claim left undecided had been supported, and if none had."""
    failed = sum(r["failed_own"] for r in rows)
    decided = sum(r["verdict_own"] for r in rows)
    open_ = sum(r[key] for r in rows for key in undecided)
    total = decided + open_
    return {
        "undecided_claims": open_,
        "if_all_supported": round(failed / total, 4) if total else None,
        "if_none_supported": round((failed + open_) / total, 4) if total else None,
    }


def measures(rows: list[dict]) -> dict[str, Any]:
    total = lambda key: sum(r[key] for r in rows)  # noqa: E731
    return {
        # D-043: the two readings of the result, side by side. The headline is the failure rate
        # among own-cited claims with a verdict. The other is the share of everything the tool
        # said that was verified against a page it cited.
        "verified_share_of_all_claims": interval(rows, lambda rs: ratio(rs, "supported", "claims")),
        "failed_share_of_all_claims": interval(rows, lambda rs: ratio(rs, "failed", "claims")),
        "labels": {
            label: {
                "claims": total(label),
                "share": round(total(label) / total("claims"), 4) if total("claims") else None,
            }
            for label in ALL_LABELS
        },
        "headline_bounds": {
            "unread_pages": bounds(rows, ("unread_own",)),
            "unread_pages_and_needs_human": bounds(rows, ("unread_own", "needs_human_own")),
        },
        "questions": len(rows),
        "claims": total("claims"),
        "with_verdict": total("with_verdict"),
        "headline_failed_share": interval(rows, lambda rs: ratio(rs, "failed_own", "verdict_own")),
        "headline_claims": total("verdict_own"),
        "paragraph_cited_failed_share": interval(
            rows, lambda rs: ratio(rs, "failed_paragraph", "verdict_paragraph")
        ),
        "paragraph_cited_claims": total("verdict_paragraph"),
        "failed_share_of_verdicts": interval(rows, lambda rs: ratio(rs, "failed", "with_verdict")),
        "contradicted": total("contradicted"),
        "shares_of_all_claims": {
            key: round(total(key) / total("claims"), 4) if total("claims") else None
            for key in (
                "partial",
                "needs_human",
                "unchecked",
                "dead_link",
                "citation_unread",
                "uncited",
            )
        },
        "claims_per_answer": round(total("claims") / len(rows), 2) if rows else None,
        "pages_cited_per_answer": round(total("pages_cited") / len(rows), 2) if rows else None,
        "pages_read_share": round(total("pages_read") / total("pages_cited"), 4)
        if total("pages_cited")
        else None,
    }


def difference(
    a: list[dict], b: list[dict], top: str = "failed_own", bottom: str = "verdict_own"
) -> dict:
    """First tool's share minus the second's, resampling the same questions for both.

    By default the headline: failed own-cited claims over own-cited claims with a verdict.
    """
    by_q = {r["id"]: r for r in b}
    pairs = [(r, by_q[r["id"]]) for r in a if r["id"] in by_q]

    def stat(ps: list[tuple[dict, dict]]) -> float | None:
        x = ratio([p[0] for p in ps], top, bottom)
        y = ratio([p[1] for p in ps], top, bottom)
        return None if x is None or y is None else x - y

    return interval(pairs, stat) | {"questions": len(pairs)}  # type: ignore[arg-type]


def pages_not_read(reports: list[dict]) -> dict[str, Any]:
    """Cited pages the fetcher could not read: how many, why, and on which sites."""
    reason_of: dict[str, str] = {}
    read: set[str] = set()
    for report in reports:
        for claim in report["claims"]:
            for page in claim["pages"]:
                if page["skipped"]:
                    reason_of[page["url"]] = page["skipped"]
                else:
                    read.add(page["url"])
    by_site: dict[str, Counter] = {}
    for url, reason in reason_of.items():
        by_site.setdefault(host_of(url), Counter())[reason] += 1
    top = sorted(by_site.items(), key=lambda kv: -sum(kv[1].values()))[:15]
    return {
        "pages_cited": len(read) + len(reason_of),
        "pages_not_read": len(reason_of),
        "by_reason": dict(Counter(reason_of.values()).most_common()),
        "sites_most_often_not_read": [
            {"site": site, "pages": sum(c.values()), "reasons": dict(c.most_common())}
            for site, c in top
        ],
    }


def summarise(which: str) -> dict[str, Any]:
    questions = load_questions(which)
    source = {q["id"]: q["source"] for q in questions}
    body: dict[str, Any] = {"set": which, "questions": len(questions), "judges": {}}
    for judge, model in JUDGES.items():
        per_tool: dict[str, Any] = {}
        rows_by_tool: dict[str, list[dict]] = {}
        for tool in TOOLS:
            rows, reports = [], []
            for q in questions:
                audit = load(audit_path(judge, tool, q["id"]))
                answer = load(answer_path(tool, q["id"]))
                if audit and answer:
                    reports.append(audit["report"])
                    rows.append(
                        {"id": q["id"], "answer_usd": answer["usd"]} | counts(audit["report"])
                    )
            rows_by_tool[tool] = rows
            if rows:
                per_tool[tool] = measures(rows) | {
                    "by_source": {
                        s: measures([r for r in rows if source[r["id"]] == s])
                        for s in ("natural_questions", "2025_2026")
                        if any(source[r["id"]] == s for r in rows)
                    },
                    "usd_per_answer": round(sum(r["answer_usd"] for r in rows) / len(rows), 4),
                    "usd_per_audit": round(sum(r["audit_usd"] for r in rows) / len(rows), 4),
                    "pages": pages_not_read(reports),
                }
        entry: dict[str, Any] = {"page_judge": model, "tools": per_tool}
        if all(rows_by_tool.get(t) for t in TOOLS):
            pair = (rows_by_tool["openai"], rows_by_tool["claude"])
            entry["openai_minus_claude"] = difference(*pair)
            entry["openai_minus_claude_verified_share_of_all_claims"] = difference(
                *pair, top="supported", bottom="claims"
            )
        body["judges"][judge] = entry
    return body


# The re-ask run: how much do the figures move when the same question is asked again?


def marker_check(raw: str, annotations: list[dict], marked: str) -> dict[str, int]:
    """Does every marker sit right after the span its annotation covers?

    Checked without the code that placed the markers: the last words of each cited span must
    appear in the marked answer with that page's number straight after them.
    """
    body, _, listing = marked.partition("\n\nSources:\n")
    number = {url: n for n, url in re.findall(r"^\[(\d+)\] (\S+)$", listing, re.MULTILINE)}
    spans = misplaced = long_spans = inline = 0
    for a in annotations:
        span = raw[a["start"] : a["end"]]
        if a["url"] in span:  # the link is already inside the span, so no marker was added
            inline += 1
            continue
        spans += 1
        tail = re.escape(raw[max(a["start"], a["end"] - 40) : a["end"]])
        runs = re.findall(tail + r"((?:\[\d+\])+)", body)
        wanted = f"[{number.get(a['url'])}]"
        misplaced += not any(wanted in run for run in runs)
        # A span of more than one sentence gets one marker, at its end. The sentences before
        # the last then have no citation of their own.
        long_spans += bool(re.search(r"[.!?][\"')\]]*\s+\S", span.strip()))
    return {
        "annotations": len(annotations),
        # The tool wrote the link into its own text, so the auditor reads the tool's placement.
        "links_the_tool_wrote_inline": inline,
        "markers_added_by_our_code": spans,
        "misplaced": misplaced,
        "spans_over_one_sentence": long_spans,
    }


def pooled(rows: list[dict]) -> list[dict]:
    """One row per question: the counts of its repeats added together."""
    by_q: dict[str, dict] = {}
    for r in rows:
        total = by_q.setdefault(r["id"], {"id": r["id"]})
        for key, value in r.items():
            if key != "id":
                total[key] = total.get(key, 0) + value
    return list(by_q.values())


def within_question_range(rows_by_repeat: dict[str, list[dict]]) -> dict[str, Any]:
    """For each question, the gap between its highest and lowest failed share across repeats."""
    shares: dict[str, list[float]] = {}
    for rows in rows_by_repeat.values():
        for r in rows:
            if r["verdict_own"]:
                shares.setdefault(r["id"], []).append(r["failed_own"] / r["verdict_own"])
    gaps = [max(v) - min(v) for v in shares.values() if len(v) >= 2]
    if not gaps:
        return {"questions": 0, "median": None, "mean": None, "max": None}
    return {
        "questions": len(gaps),
        "median": round(statistics.median(gaps), 4),
        "mean": round(statistics.mean(gaps), 4),
        "max": round(max(gaps), 4),
    }


BRIEF = (
    "questions",
    "claims",
    "headline_failed_share",
    "headline_claims",
    "verified_share_of_all_claims",
    "claims_per_answer",
    "pages_cited_per_answer",
    "pages_read_share",
)


def brief(rows: list[dict]) -> dict[str, Any]:
    m = measures(rows)
    return {key: m[key] for key in BRIEF} | {"uncited_share": m["labels"]["uncited"]["share"]}


def searches_used(answers: list[dict]) -> dict[str, Any]:
    used = [a["searches"] for a in answers if a.get("searches") is not None]
    if not used:
        return {"answers": 0}
    return {
        "answers": len(used),
        "mean": round(statistics.mean(used), 2),
        "max": max(used),
        "answers_at_or_over_the_cap": sum(n >= SEARCH_CAP for n in used),
        # An answer written without searching cites nothing, so all its claims are uncited.
        "answers_with_no_search": sum(n == 0 for n in used),
    }


def reask_tool(tool: str, chosen: list[dict], judge: str) -> tuple[dict, dict, Counter]:
    """One tool's rows for the first ask and each repeat, its summary, and its marker check."""
    names = ["first_ask"] + [f"r{n}" for n in range(1, REPEATS + 1)]
    rows: dict[str, list[dict]] = {name: [] for name in names}
    answers: list[dict] = []
    checks: Counter = Counter()
    for q in chosen:
        for name in names:
            first = name == "first_ask"
            qid, root = (q["id"], HERE) if first else (f"{q['id']}-{name}", REASK)
            audit = load(audit_path(judge, tool, qid, root))
            answer = load(answer_path(tool, qid, root))
            if not (audit and answer):
                continue
            rows[name].append(
                {"id": q["id"], "answer_usd": answer["usd"]} | counts(audit["report"])
            )
            if first:
                continue
            answers.append(answer)
            if "annotations" in answer:
                checks.update(
                    marker_check(answer["raw_text"], answer["annotations"], answer["text"])
                )
    repeats = {name: rs for name, rs in rows.items() if name != "first_ask"}
    heads = [
        v
        for rs in repeats.values()
        if rs and (v := ratio(rs, "failed_own", "verdict_own")) is not None
    ]
    every = [r for rs in repeats.values() for r in rs]
    summary = {
        "runs": {name: brief(rs) for name, rs in rows.items() if rs},
        "headline_across_repeats": {
            "min": round(min(heads), 4) if heads else None,
            "max": round(max(heads), 4) if heads else None,
        },
        "repeats_pooled": brief(pooled(every)) if every else None,
        "within_question_range_of_failed_share": within_question_range(repeats),
        "searches": searches_used(answers),
        "answers_cut_off": sum(a.get("ended") in ("incomplete", "max_tokens") for a in answers),
        "usd": {
            "answers": round(sum(a["usd"] for a in answers), 4),
            "audits": round(sum(r["audit_usd"] for r in every), 4),
        },
    }
    return rows, summary, checks


def summarise_reask(judge: str = "haiku") -> dict[str, Any]:
    chosen = choose_reask(load_questions("all"))
    body: dict[str, Any] = {
        "seed": REASK_SEED,
        "questions": [q["id"] for q in chosen],
        "repeats": REPEATS,
        "search_cap": SEARCH_CAP,
        "page_judge": JUDGES[judge],
        "note": "first_ask is the main run's answer to the same questions. OpenAI had no search "
        "cap there; in the repeats both tools are capped.",
        "tools": {},
    }
    rows_by: dict[str, dict[str, list[dict]]] = {}
    for tool in TOOLS:
        rows_by[tool], body["tools"][tool], checks = reask_tool(tool, chosen, judge)
        if tool == "openai":
            body["openai_markers"] = dict(checks)
    runs = {name: (rows_by["openai"][name], rows_by["claude"][name]) for name in rows_by["openai"]}
    # All repeats together, one row per question, so the interval still resamples questions.
    runs["repeats_pooled"] = tuple(  # type: ignore[assignment]
        pooled([r for name, rows in rows_by[tool].items() if name != "first_ask" for r in rows])
        for tool in TOOLS
    )
    runs = {name: pair for name, pair in runs.items() if pair[0] and pair[1]}
    body["openai_minus_claude"] = {name: difference(*pair) for name, pair in runs.items()}
    body["openai_minus_claude_verified_share_of_all_claims"] = {
        name: difference(*pair, top="supported", bottom="claims") for name, pair in runs.items()
    }
    return body


# Command.


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m evals realworld")
    steps = ["questions", "run", "summary", "reask", "reask-summary", "reread", "reread-summary"]
    steps += ["short", "short-summary"]
    parser.add_argument("step", choices=steps)
    parser.add_argument(
        "--limit", type=int, help="reask, reread, short: only the first N items, as a trial"
    )
    parser.add_argument("--set", choices=["pilot", "all"], default="pilot", dest="which")
    parser.add_argument("--tools", default=",".join(TOOLS))
    parser.add_argument("--cap", type=float, default=3.0, help="US dollars for the whole command")
    args = parser.parse_args(argv)
    if args.step == "questions":
        write_questions()
        return
    if args.step == "summary":
        name = "realworld" if args.which == "all" else f"realworld_{args.which}"
        path = write_result(name, summarise(args.which))
        print(f"wrote {path.name}")
        return
    if args.step == "short-summary":
        from evals.short import write_summary as write_short

        write_short()
        return
    if args.step == "reread-summary":
        from evals.reread import write_summary  # imported here: reread imports this module

        write_summary()
        return
    if args.step == "reask-summary":
        path = write_result("realworld_reask", summarise_reask())
        print(f"wrote {path.name}")
        return
    settings = load_settings(cost_cap_usd=args.cap)
    tracer = LangfuseTracer(settings)
    tools = [t for t in args.tools.split(",") if t in TOOLS]
    if args.step == "short":
        from evals.short import ShortReader

        print(f"  judging claims on short pages, cap ${args.cap:.2f}")
        try:
            with tracer.span("realworld.short", "span", {}):
                asyncio.run(ShortReader(settings, args.cap, tracer).run(args.limit))
        finally:
            tracer.flush()
        return
    if args.step == "reread":
        from evals.reread import Rereader

        print(f"  reading thin pages again in a browser, cap ${args.cap:.2f}")
        try:
            with tracer.span("realworld.reread", "span", {}):
                asyncio.run(Rereader(settings, args.cap, tracer).run(args.limit))
        finally:
            tracer.flush()
        return
    if args.step == "reask":
        # Audited with the page judge as shipped only: the question here is how much the
        # answers move, and the second judge would double the audits' cost.
        questions = reask_items(load_questions("all"))[: args.limit]
        runner = Runner(
            settings, args.cap, tracer, root=REASK, judges=("haiku",), max_searches=SEARCH_CAP
        )
        name = "realworld.reask"
    else:
        questions = load_questions(args.which)
        runner = Runner(settings, args.cap, tracer)
        name = f"realworld.{args.which}"
    print(f"  {len(questions)} questions x {len(tools)} tools, cap ${args.cap:.2f}")
    try:
        with tracer.span(name, "span", {"questions": len(questions)}):
            asyncio.run(runner.run(questions, tools))
    finally:
        tracer.flush()
