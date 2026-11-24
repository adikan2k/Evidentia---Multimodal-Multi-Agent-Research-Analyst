"""The real-world audit (D-042): ask AI tools the fixed questions, audit every answer, summarise.

    uv run python -m evals realworld questions                     # free, done once
    uv run python -m evals realworld run --set pilot --cap 3       # paid; ask first
    uv run python -m evals realworld summary --set pilot           # free

Every answer and every audit is saved, so a rerun only pays for what is missing. Each answer is
audited twice: with the page judge as shipped (Haiku) and with OpenAI's gpt-6-luna as the page
judge, to see whether a Claude judge treats Claude's answers differently.
"""

import argparse
import asyncio
import json
import random
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


def load_questions(which: str) -> list[dict]:
    rows = read_jsonl(QUESTIONS)
    if which == "pilot":
        return [q for q in rows if q["id"] in PILOT]
    return rows


def answer_path(tool: str, qid: str) -> Path:
    return HERE / "answers" / tool / f"{qid}.json"


def audit_path(judge: str, tool: str, qid: str) -> Path:
    return HERE / "audits" / judge / tool / f"{qid}.json"


def save(path: Path, body: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# Running.


class Runner:
    def __init__(self, settings: Settings, cap: float, tracer: Tracer) -> None:
        self.s = settings
        self.tracer = tracer
        self.shared = Ledger(cap)
        # One fetcher for every audit, so the wait between requests to one site holds across all.
        self.fetcher = Fetcher(settings, tracer)
        self.voyage = Embedder(settings, self.shared, tracer).client
        self.gate = asyncio.Semaphore(CONCURRENT_QUESTIONS)

    async def answer(self, tool: str, q: dict) -> dict:
        path = answer_path(tool, q["id"])
        saved = load(path)
        if saved is not None:
            return saved
        ledger = RowLedger(self.shared)
        if tool == "openai":
            got = await answer_with_web_search(q["question"], self.s, ledger)
        else:
            got = await claude_answer_with_web_search(q["question"], self.s, ledger, self.tracer)
        body = {"id": q["id"], "tool": tool} | got
        save(path, body)
        return body

    async def audit(self, tool: str, judge: str, q: dict, answer: dict) -> None:
        path = audit_path(judge, tool, q["id"])
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
                    for judge in JUDGES:
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
    return {
        "claims": len(report["claims"]),
        "with_verdict": sum(labels[label] for label in VERDICT),
        "failed": sum(labels[label] for label in FAILED),
        "contradicted": labels["contradicted"],
        "partial": labels["partial"],
        "needs_human": labels["needs_human"],
        "unchecked": labels["unchecked"],
        "dead_link": labels["dead_link"],
        "uncited": labels["uncited"],
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


def measures(rows: list[dict]) -> dict[str, Any]:
    total = lambda key: sum(r[key] for r in rows)  # noqa: E731
    return {
        "questions": len(rows),
        "claims": total("claims"),
        "with_verdict": total("with_verdict"),
        "failed_share_of_verdicts": interval(rows, lambda rs: ratio(rs, "failed", "with_verdict")),
        "contradicted": total("contradicted"),
        "shares_of_all_claims": {
            key: round(total(key) / total("claims"), 4) if total("claims") else None
            for key in ("partial", "needs_human", "unchecked", "dead_link", "uncited")
        },
        "claims_per_answer": round(total("claims") / len(rows), 2) if rows else None,
        "pages_cited_per_answer": round(total("pages_cited") / len(rows), 2) if rows else None,
        "pages_read_share": round(total("pages_read") / total("pages_cited"), 4)
        if total("pages_cited")
        else None,
    }


def difference(a: list[dict], b: list[dict]) -> dict:
    """First tool's failed share minus the second's, resampling the same questions for both."""
    by_q = {r["id"]: r for r in b}
    pairs = [(r, by_q[r["id"]]) for r in a if r["id"] in by_q]

    def stat(ps: list[tuple[dict, dict]]) -> float | None:
        x = ratio([p[0] for p in ps], "failed", "with_verdict")
        y = ratio([p[1] for p in ps], "failed", "with_verdict")
        return None if x is None or y is None else x - y

    return interval(pairs, stat) | {"questions": len(pairs)}  # type: ignore[arg-type]


def summarise(which: str) -> dict[str, Any]:
    questions = load_questions(which)
    source = {q["id"]: q["source"] for q in questions}
    body: dict[str, Any] = {"set": which, "questions": len(questions), "judges": {}}
    for judge, model in JUDGES.items():
        per_tool: dict[str, Any] = {}
        rows_by_tool: dict[str, list[dict]] = {}
        for tool in TOOLS:
            rows = []
            for q in questions:
                audit = load(audit_path(judge, tool, q["id"]))
                answer = load(answer_path(tool, q["id"]))
                if audit and answer:
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
                }
        entry: dict[str, Any] = {"page_judge": model, "tools": per_tool}
        if all(rows_by_tool.get(t) for t in TOOLS):
            entry["openai_minus_claude"] = difference(
                rows_by_tool["openai"], rows_by_tool["claude"]
            )
        body["judges"][judge] = entry
    return body


# Command.


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m evals realworld")
    parser.add_argument("step", choices=["questions", "run", "summary"])
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
    settings = load_settings(cost_cap_usd=args.cap)
    tracer = LangfuseTracer(settings)
    questions = load_questions(args.which)
    tools = [t for t in args.tools.split(",") if t in TOOLS]
    print(f"  {len(questions)} questions x {len(tools)} tools, cap ${args.cap:.2f}")
    try:
        with tracer.span(f"realworld.{args.which}", "span", {"questions": len(questions)}):
            asyncio.run(Runner(settings, args.cap, tracer).run(questions, tools))
    finally:
        tracer.flush()
