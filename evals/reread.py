"""Read the thin pages again with the browser, and judge the claims they left stranded (D-046).

    uv run python -m evals realworld reread --cap 1        # paid; ask first
    uv run python -m evals realworld reread-summary        # free

Some cited pages gave the fetcher too little text, so their claims got no verdict. Here each such
page is rendered in a headless browser (`evidentia/render.py`). Only the claim-and-page pairs that
had been skipped for too little text are judged. Every other claim keeps the label it had, so the
change in the figures is the reader's doing and not the judges' run-to-run noise.

The saved audits are not changed. New reports go under `evals/realworld/rendered/`.
"""

import asyncio
import copy
from collections import Counter
from pathlib import Path
from typing import Any

from evals.aggrefact import RowLedger
from evals.common import write_result
from evals.realworld import (
    CONCURRENT_QUESTIONS,
    HERE,
    JUDGES,
    REASK,
    TOOLS,
    VERDICT,
    audit_path,
    counts,
    difference,
    load,
    load_questions,
    measures,
    pooled,
    reask_items,
    save,
)
from evidentia.audit.events import page_view
from evidentia.audit.graph import TOO_LITTLE_TEXT, AuditDeps, AuditNodes, page_first
from evidentia.audit.schemas import RANK
from evidentia.config import Settings
from evidentia.cost import BudgetExceeded, Ledger
from evidentia.embed import Embedder
from evidentia.fetch import NO_READABLE_TEXT, Fetcher, Skip
from evidentia.llm import LLM
from evidentia.render import Renderer
from evidentia.schemas import Source
from evidentia.tracing import Tracer

RENDERED = HERE / "rendered"
JUDGE = "haiku"  # the page judge as shipped
# A page that answered but gave too little text: under 200 characters, or under 2,000.
RETRY = {TOO_LITTLE_TEXT, NO_READABLE_TEXT}
STILL_THIN = "still too little text after the browser ran the page"
RUNS = ("main", "reask")


def items(run: str) -> list[dict]:
    """Every audited answer of a run: its file name, and the question it answers."""
    questions = load_questions("all")
    if run == "reask":
        return [{"id": q["id"], "of": q["of"]} for q in reask_items(questions)]
    return [{"id": q["id"], "of": q["id"]} for q in questions]


def root_of(run: str) -> Path:
    return REASK if run == "reask" else HERE


def rendered_path(run: str, tool: str, qid: str) -> Path:
    return RENDERED / run / tool / f"{qid}.json"


def thin_pages(report: dict) -> list[str]:
    """The cited pages of one audit that answered with too little text, each once."""
    urls = [p["url"] for c in report["claims"] for p in c["pages"] if p["skipped"] in RETRY]
    return list(dict.fromkeys(urls))


def relabel(claim: dict) -> str:
    """A claim's label from its pages, by the auditor's own rule (`claim_label`)."""
    labels = {p["label"] for p in claim["pages"]}
    if not claim["citation_ids"] or not labels:
        return claim["label"]
    return next(label for label in RANK if label in labels)


def with_new_pages(report: dict, judged: dict[tuple[int, str], dict], read: int) -> dict:
    """A copy of the report with the re-judged pages put in and the claims' labels redone."""
    new = copy.deepcopy(report)
    for (index, url), view in judged.items():
        claim = new["claims"][index]
        claim["pages"] = [view if p["url"] == url else p for p in claim["pages"]]
        claim["label"] = relabel(claim)
    new["scorecard"]["pages_read"] = report["scorecard"]["pages_read"] + read
    return new


class Rereader:
    def __init__(self, settings: Settings, cap: float, tracer: Tracer) -> None:
        self.s = settings
        self.tracer = tracer
        self.shared = Ledger(cap)
        self.fetcher = Fetcher(settings, tracer)
        self.renderer = Renderer(settings, self.fetcher, tracer)
        self.voyage = Embedder(settings, self.shared, tracer).client
        self.gate = asyncio.Semaphore(CONCURRENT_QUESTIONS)
        self._pages: dict[str, asyncio.Task[Source | Skip]] = {}

    async def page(self, url: str) -> Source | Skip:
        """Each page is rendered once, however many answers cite it."""
        if url not in self._pages:
            self._pages[url] = asyncio.create_task(self._render(url))
        return await self._pages[url]

    async def _render(self, url: str) -> Source | Skip:
        got = await self.renderer.render(url)
        if isinstance(got, Source) and len(got.text) < self.s.audit_min_page_chars:
            return Skip(STILL_THIN)
        return got

    async def one(self, run: str, tool: str, item: dict) -> None:
        path = rendered_path(run, tool, item["id"])
        audit = load(audit_path(JUDGE, tool, item["id"], root_of(run)))
        if path.exists() or audit is None or not thin_pages(audit["report"]):
            return
        report = audit["report"]
        async with self.gate:
            got = {url: await self.page(url) for url in thin_pages(report)}
            sources = {url: s for url, s in got.items() if isinstance(s, Source)}
            ledger = RowLedger(self.shared)
            judged = await self.judge(report, sources, ledger, f"reread-{run}-{tool}-{item['id']}")
        body = {
            "id": item["id"],
            "tool": tool,
            "run": run,
            "judge": JUDGES[JUDGE],
            "pages": [
                {"url": url, "read": url in sources}
                | ({"chars": len(s.text)} if isinstance(s, Source) else {"why_not": s.reason})
                for url, s in got.items()
            ],
            "usd": round(ledger.spent, 6),
            "report": with_new_pages(report, judged, len(sources)),
        }
        save(path, body)
        print(f"  {run} {item['id']} {tool}: {len(sources)} of {len(got)} pages read")

    async def judge(
        self, report: dict, sources: dict[str, Source], ledger: Ledger, run_id: str
    ) -> dict[tuple[int, str], dict]:
        """Both judges, for each claim-and-page pair that had been skipped as too thin."""
        deps = AuditDeps(
            settings=self.s,
            ledger=ledger,
            tracer=self.tracer,
            llm=LLM(self.s, ledger),
            fetcher=self.fetcher,
            embedder=Embedder(self.s, ledger, self.tracer, client=self.voyage),
        )
        nodes = AuditNodes(deps)
        todo = [
            (index, page)
            for index, claim in enumerate(report["claims"])
            for page in claim["pages"]
            if page["skipped"] in RETRY and page["url"] in sources
        ]

        async def one(n: int) -> dict:
            index, page = todo[n]
            claim, source = report["claims"][index]["claim"], sources[page["url"]]
            result = await nodes.assess(claim, source, run_id)
            fields = await nodes.page_verdict(claim, source, run_id, None)
            result = result.model_copy(update=fields | {"citation_id": page["citation_id"]})
            dumped = result.model_dump() | {
                "label": result.label,
                "quote_label": result.quote_label,
            }
            return page_view(dumped, source) | {"read_by": "render"}

        views = await page_first(list(range(len(todo))), lambda n: todo[n][1]["url"], one)
        return {(index, page["url"]): view for (index, page), view in zip(todo, views, strict=True)}

    def jobs(self) -> list[tuple[str, str, dict]]:
        """The answers that cite a thin page and have not been read again yet."""
        found = []
        for run in RUNS:
            for tool in TOOLS:
                for item in items(run):
                    audit = load(audit_path(JUDGE, tool, item["id"], root_of(run)))
                    done = rendered_path(run, tool, item["id"]).exists()
                    if audit and not done and thin_pages(audit["report"]):
                        found.append((run, tool, item))
        return found

    async def run(self, limit: int | None = None) -> None:
        jobs = self.jobs()[:limit]
        print(f"  {len(jobs)} answers to look at again")
        try:
            async with asyncio.TaskGroup() as group:
                for job in jobs:
                    group.create_task(self.safely(*job))
        except* BudgetExceeded as errors:
            print(f"  stopped at the cap: {errors.exceptions[0]}")
        finally:
            await self.renderer.aclose()
            await self.fetcher.aclose()
        print(f"  spent ${self.shared.spent:.4f} this command")

    async def safely(self, run: str, tool: str, item: dict) -> None:
        try:
            await self.one(run, tool, item)
        except BudgetExceeded:
            raise
        except Exception as err:  # saved work stays; a rerun tries the rest again
            print(f"  {run} {item['id']} {tool}: {type(err).__name__}: {str(err)[:120]}")


# Summarising.


def gained(before: dict, after: dict) -> Counter:
    """The new labels of the claims whose label changed."""
    return Counter(
        f"{b['label']} -> {a['label']}"
        for b, a in zip(before["claims"], after["claims"], strict=True)
        if b["label"] != a["label"]
    )


def figures(rows: list[dict]) -> dict[str, Any]:
    m = measures(rows)
    return {
        "headline_failed_share": m["headline_failed_share"],
        "headline_claims": m["headline_claims"],
        "verified_share_of_all_claims": m["verified_share_of_all_claims"],
        "headline_bounds_unread_pages": m["headline_bounds"]["unread_pages"],
        "pages_read_share": m["pages_read_share"],
    }


def summarise_run(run: str) -> dict[str, Any]:
    outcome: dict[str, str] = {}
    body: dict[str, Any] = {"tools": {}}
    rows: dict[str, dict[str, list[dict]]] = {}
    for tool in TOOLS:
        before, after = [], []
        changes: Counter = Counter()
        answers = usd = 0
        for item in items(run):
            audit = load(audit_path(JUDGE, tool, item["id"], root_of(run)))
            if audit is None:
                continue
            again = load(rendered_path(run, tool, item["id"]))
            new = again["report"] if again else audit["report"]
            before.append({"id": item["of"], "answer_usd": 0.0} | counts(audit["report"]))
            after.append({"id": item["of"], "answer_usd": 0.0} | counts(new))
            if again:
                answers += 1
                usd += again["usd"]
                changes.update(gained(audit["report"], new))
                for page in again["pages"]:
                    outcome[page["url"]] = "read" if page["read"] else page["why_not"]
        rows[tool] = {"before": pooled(before), "after": pooled(after)}
        body["tools"][tool] = {
            "answers_with_a_thin_page": answers,
            "claims_whose_label_changed": sum(changes.values()),
            "claims_that_gained_a_verdict": sum(
                n for change, n in changes.items() if change.split(" -> ")[1] in VERDICT
            ),
            "changes": dict(changes.most_common()),
            "before": figures(rows[tool]["before"]),
            "after": figures(rows[tool]["after"]),
            "usd": round(usd, 4),
        }
    body["pages"] = {
        "tried": len(outcome),
        "read": sum(v == "read" for v in outcome.values()),
        "not_read": dict(Counter(v for v in outcome.values() if v != "read").most_common()),
    }
    body["openai_minus_claude"] = {
        when: difference(rows["openai"][when], rows["claude"][when])
        for when in ("before", "after")
        if rows["openai"][when] and rows["claude"][when]
    }
    return body


def summarise() -> dict[str, Any]:
    return {
        "page_judge": JUDGES[JUDGE],
        "note": "Only claim-and-page pairs skipped for too little text were judged again, "
        "against the page as a headless browser rendered it. Every other label is unchanged. "
        "In the re-ask run a question's repeats are pooled.",
        "runs": {run: summarise_run(run) for run in RUNS},
    }


def write_summary() -> None:
    path = write_result("realworld_rendered", summarise())
    print(f"wrote {path.name}")
