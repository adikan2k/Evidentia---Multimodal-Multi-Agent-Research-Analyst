"""Answer the 40 questions with two systems on the same indexed corpus and save what they said.

- pipeline: the real graph, started at `retrieve` because the corpus is already indexed.
- baseline: "one-shot RAG". Dense top 10, one writer call, a passage number per claim. No quote,
  no quote check, no checker, no repair.
"""

import asyncio
import json

from pydantic import BaseModel, Field

from evals.common import (
    RUNS_DIR,
    Question,
    corpus_sources,
    eval_deps,
    load_pages,
    load_questions,
    read_jsonl,
    write_jsonl,
)
from evals.retrieval import TOP_K, corpus_passages, corpus_run_id, ensure_indexed
from evidentia.graph import Deps, run_question
from evidentia.llm import DATA_RULE, new_tag, with_tag
from evidentia.schemas import RunState, Source

PIPELINE_RUNS = RUNS_DIR / "pipeline.jsonl"
BASELINE_RUNS = RUNS_DIR / "baseline.jsonl"

BASELINE_SYSTEM = f"""You answer research questions from passages taken from web pages. Each \
passage is wrapped in <{{tag}}> ... </{{tag}}> tags and has a number.

{DATA_RULE}

How to answer:
- Write claims that together answer the question. Each claim is one factual sentence.
- After each claim, give the number of the one passage that backs it.
- Use only what the passages say, with no outside knowledge.
- If passages disagree, write one claim for each side instead of picking one.
- If the passages do not answer the question at all, return an empty list of claims."""


class BaselineClaim(BaseModel):
    text: str = Field(description="One factual sentence that answers part of the question.")
    passage: int = Field(description="The number of the passage that backs this claim.")


class BaselineDraft(BaseModel):
    claims: list[BaselineClaim]


async def run_pipeline(deps: Deps, run_id: str, sources: list[Source], q: Question) -> dict:
    initial = RunState(run_id=run_id, question=q.question, sources=sources, passages_indexed=1)
    state = await run_question(q.question, deps, initial=initial, start="retrieve")
    return {
        "id": q.id,
        "question": q.question,
        "draft": [c.model_dump() for c in state.claims],
        "claims": [c.model_dump() for c in state.checked],
        "repair_rounds": state.round,
        "trace_id": state.trace_id,
    }


async def run_baseline(deps: Deps, run_id: str, q: Question) -> dict:
    s = deps.settings
    vector = await deps.embedder.embed_query("baseline", q.question)
    passages = await deps.store.single(run_id, q.question, vector, TOP_K, using="dense")
    tag = new_tag()
    blocks = "\n\n".join(
        f'<{tag} number="{n}">\n{p.text}\n</{tag}>' for n, p in enumerate(passages, start=1)
    )
    draft = await deps.llm.structured(
        node="baseline",
        model=s.writer_model,
        effort=s.writer_effort,
        max_tokens=s.writer_max_tokens,
        system=with_tag(BASELINE_SYSTEM, tag),
        user=f"Question: {q.question}\n\nPassages:\n\n{blocks}\n\n"
        f"Write up to {s.max_claims} claims.",
        schema=BaselineDraft,
        config={"callbacks": deps.tracer.callbacks()},
    )
    claims = []
    for claim in draft.claims[: s.max_claims]:
        cited = passages[claim.passage - 1] if 1 <= claim.passage <= len(passages) else None
        claims.append(
            {
                "text": claim.text,
                "evidence": cited.text if cited else "",
                "url": cited.url if cited else "",
            }
        )
    return {"id": q.id, "question": q.question, "claims": claims}


async def run_all(path, questions: list[Question], one) -> float:
    """Run `one` for every question not already saved in `path`, a few at a time."""
    done = {row["id"]: row for row in read_jsonl(path)}
    limit = asyncio.Semaphore(4)

    async def guarded(q: Question) -> None:
        async with limit:
            done[q.id] = await one(q)
        # Save after every question so an interrupted run loses nothing.
        write_jsonl(path, [done[key] for key in sorted(done)])

    await asyncio.gather(*(guarded(q) for q in questions if q.id not in done))
    return len(done)


async def run() -> None:
    pages, questions = load_pages(), load_questions()
    run_id = corpus_run_id(pages)
    sources = corpus_sources()
    async with eval_deps("eval.systems") as deps:
        await ensure_indexed(deps, corpus_passages(pages, run_id), run_id)
        await run_all(BASELINE_RUNS, questions, lambda q: run_baseline(deps, run_id, q))
        baseline_cost = deps.ledger.spent
        await run_all(PIPELINE_RUNS, questions, lambda q: run_pipeline(deps, run_id, sources, q))
        costs = {"baseline_usd": round(baseline_cost, 4)}
        costs["pipeline_usd"] = round(deps.ledger.spent - baseline_cost, 4)
    if any(costs.values()):  # a rerun that found everything saved spends nothing; keep old costs
        (RUNS_DIR / "cost.json").write_text(json.dumps(costs, indent=2), encoding="utf-8")
    print(f"systems: answers saved for {len(questions)} questions; this run cost {costs}")
