"""Judge the claims left stranded on short pages, as a third reading (D-047).

    uv run python -m evals realworld short --cap 0.6       # paid; ask first
    uv run python -m evals realworld short-summary         # free

After the browser re-read (D-046), some cited pages still give under 2,000 characters: short
articles, abstracts, paywall teasers. The auditor gives their claims no verdict. Here each such
page is fetched again as plain text and only the stranded claim-and-page pairs are judged, by
both judges as shipped. Every other claim keeps its label.

This is a check on the headline, not a new headline: on a paywall teaser a claim the full article
backs would be marked "not on the cited page". The saved audits are not changed.
"""

import asyncio
from collections import Counter
from pathlib import Path
from typing import Any

from evals.aggrefact import RowLedger
from evals.common import write_result
from evals.realworld import (
    CONCURRENT_QUESTIONS,
    HERE,
    JUDGES,
    TOOLS,
    VERDICT,
    audit_path,
    counts,
    difference,
    load,
    measures,
    pooled,
    save,
)
from evals.reread import (
    JUDGE,
    RUNS,
    gained,
    items,
    judge_stranded,
    rendered_path,
    root_of,
    thin_pages,
    with_new_pages,
)
from evidentia.audit.graph import AuditDeps
from evidentia.config import Settings
from evidentia.cost import BudgetExceeded, Ledger
from evidentia.embed import Embedder
from evidentia.fetch import Fetcher
from evidentia.llm import LLM
from evidentia.schemas import SearchHit, Source
from evidentia.tracing import Tracer

SHORT = HERE / "short"
UNDER = 1_000  # pages this short are reported apart: the likeliest to be teasers


def short_path(run: str, tool: str, qid: str) -> Path:
    return SHORT / run / tool / f"{qid}.json"


def base_report(run: str, tool: str, qid: str) -> dict | None:
    """The audit as it stands after the browser re-read, or as saved if no page needed one."""
    again = load(rendered_path(run, tool, qid))
    if again:
        return again["report"]
    audit = load(audit_path(JUDGE, tool, qid, root_of(run)))
    return audit["report"] if audit else None


def saved_report(run: str, tool: str, qid: str) -> dict | None:
    audit = load(audit_path(JUDGE, tool, qid, root_of(run)))
    return audit["report"] if audit else None


class ShortReader:
    def __init__(self, settings: Settings, cap: float, tracer: Tracer) -> None:
        self.s = settings
        self.tracer = tracer
        self.shared = Ledger(cap)
        self.fetcher = Fetcher(settings, tracer)
        self.voyage = Embedder(settings, self.shared, tracer).client
        self.gate = asyncio.Semaphore(CONCURRENT_QUESTIONS)
        self._pages: dict[str, asyncio.Task[Source | str]] = {}

    async def page(self, url: str) -> Source | str:
        """The page as the plain fetcher reads it, once however many answers cite it."""
        if url not in self._pages:
            self._pages[url] = asyncio.create_task(self._fetch(url))
        return await self._pages[url]

    async def _fetch(self, url: str) -> Source | str:
        sources, skipped = await self.fetcher.fetch_all([SearchHit(url=url)])
        return sources[0] if sources else skipped[0].reason

    def jobs(self) -> list[tuple[str, str, dict]]:
        found = []
        for run in RUNS:
            for tool in TOOLS:
                for item in items(run):
                    report = base_report(run, tool, item["id"])
                    done = short_path(run, tool, item["id"]).exists()
                    if report and not done and thin_pages(report):
                        found.append((run, tool, item))
        return found

    async def one(self, run: str, tool: str, item: dict) -> None:
        report = base_report(run, tool, item["id"])
        assert report is not None
        async with self.gate:
            got = {url: await self.page(url) for url in thin_pages(report)}
            sources = {url: s for url, s in got.items() if isinstance(s, Source)}
            ledger = RowLedger(self.shared)
            deps = AuditDeps(
                settings=self.s,
                ledger=ledger,
                tracer=self.tracer,
                llm=LLM(self.s, ledger),
                fetcher=self.fetcher,
                embedder=Embedder(self.s, ledger, self.tracer, client=self.voyage),
            )
            run_id = f"short-{run}-{tool}-{item['id']}"
            judged = await judge_stranded(deps, report, sources, run_id, "fetch (short page)")
        save(
            short_path(run, tool, item["id"]),
            {
                "id": item["id"],
                "tool": tool,
                "run": run,
                "judge": JUDGES[JUDGE],
                "pages": [
                    {"url": url, "read": isinstance(s, Source)}
                    | ({"chars": len(s.text)} if isinstance(s, Source) else {"why_not": s})
                    for url, s in got.items()
                ],
                "usd": round(ledger.spent, 6),
                "report": with_new_pages(report, judged, len(sources)),
            },
        )
        print(f"  {run} {item['id']} {tool}: {len(judged)} claims judged on {len(sources)} pages")

    async def safely(self, run: str, tool: str, item: dict) -> None:
        try:
            await self.one(run, tool, item)
        except BudgetExceeded:
            raise
        except Exception as err:  # saved work stays; a rerun tries the rest again
            print(f"  {run} {item['id']} {tool}: {type(err).__name__}: {str(err)[:120]}")

    async def run(self, limit: int | None = None) -> None:
        jobs = self.jobs()[:limit]
        print(f"  {len(jobs)} answers with a short page")
        try:
            async with asyncio.TaskGroup() as group:
                for job in jobs:
                    group.create_task(self.safely(*job))
        except* BudgetExceeded as errors:
            print(f"  stopped at the cap: {errors.exceptions[0]}")
        finally:
            await self.fetcher.aclose()
        print(f"  spent ${self.shared.spent:.4f} this command")


# Summarising.

READINGS = ("saved", "after_browser", "with_short_pages")


def figures(rows: list[dict]) -> dict[str, Any]:
    m = measures(rows)
    return {
        "headline_failed_share": m["headline_failed_share"],
        "headline_claims": m["headline_claims"],
        "verified_share_of_all_claims": m["verified_share_of_all_claims"],
        "headline_bounds_unread_pages": m["headline_bounds"]["unread_pages"],
    }


def summarise_run(run: str) -> dict[str, Any]:
    lengths: dict[str, int | str] = {}
    rows: dict[str, dict[str, list[dict]]] = {}
    body: dict[str, Any] = {"tools": {}}
    for tool in TOOLS:
        rows[tool] = {reading: [] for reading in READINGS}
        changes: Counter = Counter()
        usd = 0.0
        for item in items(run):
            saved = saved_report(run, tool, item["id"])
            if saved is None:
                continue
            browser = base_report(run, tool, item["id"]) or saved
            again = load(short_path(run, tool, item["id"]))
            short = again["report"] if again else browser
            for reading, report in zip(READINGS, (saved, browser, short), strict=True):
                rows[tool][reading].append({"id": item["of"], "answer_usd": 0.0} | counts(report))
            if again:
                usd += again["usd"]
                changes.update(gained(browser, short))
                for page in again["pages"]:
                    lengths[page["url"]] = page["chars"] if page["read"] else page["why_not"]
        by_q = {reading: pooled(rs) for reading, rs in rows[tool].items()}
        rows[tool] = by_q
        body["tools"][tool] = {reading: figures(by_q[reading]) for reading in READINGS} | {
            "claims_whose_label_changed": sum(changes.values()),
            "claims_that_gained_a_verdict": sum(
                n for change, n in changes.items() if change.split(" -> ")[1] in VERDICT
            ),
            "changes": dict(changes.most_common()),
            "usd": round(usd, 4),
        }
    read = [v for v in lengths.values() if isinstance(v, int)]
    body["pages"] = {
        "tried": len(lengths),
        "read": len(read),
        f"read_under_{UNDER}_chars": sum(n < UNDER for n in read),
        "not_read": dict(Counter(v for v in lengths.values() if isinstance(v, str)).most_common()),
    }
    body["openai_minus_claude"] = {
        reading: difference(rows["openai"][reading], rows["claude"][reading])
        for reading in READINGS
    }
    body["openai_minus_claude_verified_share_of_all_claims"] = {
        reading: difference(
            rows["openai"][reading], rows["claude"][reading], top="supported", bottom="claims"
        )
        for reading in READINGS
    }
    return body


def summarise() -> dict[str, Any]:
    return {
        "page_judge": JUDGES[JUDGE],
        "readings": {
            "saved": "the audits as saved: the headline",
            "after_browser": "with pages a headless browser could read judged (D-046)",
            "with_short_pages": "and claims on pages of 200 to 1,999 characters judged too "
            "(D-047). A check on the headline, not a new one: teasers are judged as if complete.",
        },
        "note": "In the re-ask run a question's repeats are pooled.",
        "runs": {run: summarise_run(run) for run in RUNS},
    }


def write_summary() -> None:
    path = write_result("realworld_short", summarise())
    print(f"wrote {path.name}")
