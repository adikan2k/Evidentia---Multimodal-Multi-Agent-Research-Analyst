"""The research agent on the open web (D-052).

20 of the 40 clean-corpus questions, but the agent starts from "plan": it searches
the live web and reads what it finds, as the site does. Plain RAG then answers each question from
the passages the agent fetched and indexed for that question, so both see the same evidence. The
same judge as on the clean pages scores both.

    uv run python -m evals open-web        # paid: about $4.50, hard cap $6 (OPEN_WEB_CAP_USD)

Set OPEN_WEB_LIMIT to run only the first few questions, for a trial.
"""

import asyncio
import os
import random
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

from evals.common import (
    RUNS_DIR,
    Question,
    eval_deps,
    load_questions,
    read_jsonl,
    write_jsonl,
    write_result,
)
from evals.judge import JUDGE_MODEL, describe_system, judge_all, paired, presented
from evals.systems import run_baseline
from evidentia.graph import Deps, run_question
from evidentia.schemas import RunState

CAP_USD = float(os.environ.get("OPEN_WEB_CAP_USD", "6"))
LIMIT = int(os.environ.get("OPEN_WEB_LIMIT", "0"))  # a trial on the first few questions
# 20 of the 40, as approved for cost (D-052), drawn with a fixed seed in the corpus's own mix of
# 3 factual questions to 1 contested one.
SAMPLE = {"factual": 15, "contested": 5}
SEED = 20261126
# A trial keeps its own files, so the full run measures each system's whole cost.
NAME = "open_web_trial" if LIMIT else "open_web"
PIPELINE_RUNS = RUNS_DIR / f"{NAME}_pipeline.jsonl"
BASELINE_RUNS = RUNS_DIR / f"{NAME}_baseline.jsonl"
CONCURRENT = 4


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").removeprefix("www.")


async def ask_agent(deps: Deps, q: Question) -> dict:
    """One question from "plan" on the live web. The run's passages stay indexed for plain RAG."""
    run_id = f"open-web-{q.id}-{uuid.uuid4().hex[:8]}"
    state = await run_question(
        q.question, deps, initial=RunState(run_id=run_id, question=q.question)
    )
    return {
        "id": q.id,
        "question": q.question,
        "run_id": run_id,
        "read_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "queries": state.queries,
        "pages_read": [{"url": s.url, "kind": s.kind} for s in state.sources],
        "pages_not_read": [{"url": s.url, "reason": s.reason} for s in state.skipped],
        "claims": [c.model_dump() for c in state.checked],
        "repair_rounds": state.round,
        "trace_id": state.trace_id,
    }


async def ask_plain_rag(deps: Deps, agent_row: dict, q: Question) -> dict:
    """Plain RAG over the passages the agent indexed for this question, which are then removed."""
    answer = await run_baseline(deps, agent_row["run_id"], q)
    await deps.store.delete_run(agent_row["run_id"])
    return answer


async def run_each(
    path: Path, questions: list[Question], one: Callable[[Question], Awaitable[dict]]
) -> int:
    """Run `one` for every question not yet saved in `path`, saving after each."""
    done = {row["id"]: row for row in read_jsonl(path)}
    todo = [q for q in questions if q.id not in done]
    limit = asyncio.Semaphore(CONCURRENT)

    async def guarded(q: Question) -> None:
        async with limit:
            done[q.id] = await one(q)
        write_jsonl(path, [done[key] for key in sorted(done)])

    await asyncio.gather(*(guarded(q) for q in todo))
    return len(todo)


def items_of(rows: list[dict], system: str, kind: str) -> list[dict]:
    """Every claim one system made, with the evidence it points to (as `evals.judge` expects)."""
    items = []
    for row in rows:
        for n, claim in enumerate(row["claims"]):
            if kind == "baseline":
                evidence, label = claim["evidence"], "presented"
            else:
                evidence = claim["quote"] if claim["quote_found"] else ""
                label = claim["label"]
            items.append(
                {
                    "key": f"{system}:{row['id']}:{n}",
                    "system": system,
                    "question_id": row["id"],
                    "label": label,
                    "claim": claim["text"],
                    "evidence": evidence,
                }
            )
    return items


def page_stats(rows: list[dict]) -> dict:
    """What the agent fetched: read, not read and why, and how much of it was Wikipedia."""
    read = [p for row in rows for p in row["pages_read"]]
    not_read = [p for row in rows for p in row["pages_not_read"]]
    wiki = sum(host(p["url"]).endswith("wikipedia.org") for p in read)
    hosts = Counter(host(p["url"]) for p in read)
    return {
        "pages_read": len(read),
        "pages_not_read": len(not_read),
        "not_read_by_reason": dict(Counter(p["reason"] for p in not_read).most_common()),
        "pdfs_read": sum(p["kind"] == "pdf" for p in read),
        "wikipedia_share_of_pages_read": round(wiki / len(read), 4) if read else 0.0,
        "different_sites_read": len(hosts),
        "pages_read_per_question_median": median([len(r["pages_read"]) for r in rows])
        if rows
        else 0,
        "questions_with_a_repair_round": sum(r.get("repair_rounds", 0) > 0 for r in rows),
    }


def summarise(pipeline: list[dict], baseline: list[dict], verdicts: dict, costs: dict) -> dict:
    ids = sorted(row["id"] for row in pipeline)
    judged = {}
    for system, rows, kind in (
        ("open_web_baseline", baseline, "baseline"),
        ("open_web_pipeline", pipeline, "pipeline"),
    ):
        items = [i | verdicts[i["key"]] for i in items_of(rows, system, kind)]
        judged[system] = items
    agent = judged["open_web_pipeline"]
    return {
        "systems": {
            name: describe_system(items, ids, costs.get(name)) for name, items in judged.items()
        },
        "accuracy_difference_from_baseline": {
            "open_web_pipeline": paired(
                presented(agent), presented(judged["open_web_baseline"]), ids
            )
        },
        "unverified_share_of_agent_claims": round(
            sum(i["label"] == "unverified" for i in agent) / len(agent), 4
        )
        if agent
        else 0.0,
        "pages": page_stats(pipeline),
        "questions": len(ids),
        "read_between": [min(r["read_at"] for r in pipeline), max(r["read_at"] for r in pipeline)],
    }


def sample(questions: list[Question]) -> list[Question]:
    """The fixed sample: the same questions every time, in the corpus's mix of kinds."""
    rng = random.Random(SEED)
    chosen = []
    for kind, n in SAMPLE.items():
        chosen += rng.sample([q for q in questions if q.kind == kind], n)
    return sorted(chosen, key=lambda q: q.id)


async def run() -> None:
    questions = load_questions()
    questions = questions[:LIMIT] if LIMIT else sample(questions)
    async with eval_deps("eval.open_web", cap_usd=CAP_USD) as deps:
        costs: dict[str, float] = {}

        before = deps.ledger.spent
        ran = await run_each(PIPELINE_RUNS, questions, lambda q: ask_agent(deps, q))
        if ran == len(questions):  # a partial rerun would understate the cost
            costs["open_web_pipeline"] = deps.ledger.spent - before
        pipeline = {row["id"]: row for row in read_jsonl(PIPELINE_RUNS)}

        before = deps.ledger.spent
        ran = await run_each(
            BASELINE_RUNS, questions, lambda q: ask_plain_rag(deps, pipeline[q.id], q)
        )
        if ran == len(questions):
            costs["open_web_baseline"] = deps.ledger.spent - before

        wanted = {q.id for q in questions}
        pipeline_rows = [r for r in read_jsonl(PIPELINE_RUNS) if r["id"] in wanted]
        baseline_rows = [r for r in read_jsonl(BASELINE_RUNS) if r["id"] in wanted]
        items = items_of(pipeline_rows, "open_web_pipeline", "pipeline")
        items += items_of(baseline_rows, "open_web_baseline", "baseline")
        verdicts = await judge_all(deps, items)
        spent = deps.ledger.spent

    body = summarise(pipeline_rows, baseline_rows, verdicts, costs)
    path = write_result(
        NAME,
        {
            "what": "The research agent from plan on the live web, and plain RAG over the pages "
            "the agent fetched for each question. The same questions and judge as the "
            "clean-corpus evals (D-052).",
            "judge": f"{JUDGE_MODEL} with the checker's rubric.",
            "presented_as_backed": "all claims for plain RAG; claims labelled supported for "
            "the agent",
            "interval": "95% bootstrap over questions, 2000 resamples",
            "not_repeatable": "Search results and pages change; the fetched addresses and "
            "when they were read are in evals/runs/open_web_pipeline.jsonl.",
            **body,
            "cost_usd": round(spent, 4),
        },
    )
    print(f"open-web: wrote {path} (cost ${spent:.2f})")
