"""Answer the eval questions with several systems on the same indexed corpus and save the output.

Two kinds of system:
- baseline: "one-shot RAG". Dense top 10, one writer call, a passage number per claim. No quote,
  no quote check, no checker, no repair.
- pipeline: the real graph, started at `retrieve` because the corpus is already indexed.

Variants change one or two settings, such as a cheaper writer (D-022) or tightening (D-023).
"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel, Field

from evals.common import (
    QUESTIONS,
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
from evals.unanswerable import UNANSWERABLE
from evidentia.graph import Deps, run_question
from evidentia.llm import DATA_RULE, new_tag, with_tag
from evidentia.schemas import RunState, Source

HAIKU = "claude-haiku-5-5"
# name -> (kind, settings that differ from the defaults)
VARIANTS: dict[str, tuple[str, dict]] = {
    "baseline": ("baseline", {}),
    # Saved before keyword search was switched off by default, so it is pinned on here. The
    # retrieval eval found the two give the same top 10 once the reranker is used.
    "pipeline": ("pipeline", {"keyword_search": True, "tighten_partial": False}),
    "baseline_haiku": ("baseline", {"writer_model": HAIKU}),
    "pipeline_haiku": (
        "pipeline",
        {"writer_model": HAIKU, "checker_model": HAIKU, "tighten_partial": False},
    ),
    "pipeline_tighten": ("pipeline", {"tighten_partial": True}),
}
# question set -> (file, variants run on it)
SETS: dict[str, tuple[Path, list[str]]] = {
    "main": (QUESTIONS, list(VARIANTS)),
    "unanswerable": (UNANSWERABLE, ["baseline", "pipeline", "baseline_haiku", "pipeline_haiku"]),
}
COSTS = RUNS_DIR / "cost.json"


def runs_path(set_name: str, variant: str) -> Path:
    name = variant if set_name == "main" else f"{set_name}_{variant}"
    return RUNS_DIR / f"{name}.jsonl"


BASELINE_RUNS = runs_path("main", "baseline")
PIPELINE_RUNS = runs_path("main", "pipeline")

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
        evidence = {"evidence": cited.text if cited else "", "url": cited.url if cited else ""}
        claims.append({"text": claim.text} | evidence)
    return {"id": q.id, "question": q.question, "claims": claims}


async def run_all(path: Path, questions: list[Question], one) -> int:
    """Run `one` for every question not already saved in `path`. Returns how many it ran."""
    done = {row["id"]: row for row in read_jsonl(path)}
    todo = [q for q in questions if q.id not in done]
    limit = asyncio.Semaphore(4)

    async def guarded(q: Question) -> None:
        async with limit:
            done[q.id] = await one(q)
        # Save after every question so an interrupted run loses nothing.
        write_jsonl(path, [done[key] for key in sorted(done)])

    await asyncio.gather(*(guarded(q) for q in todo))
    return len(todo)


def record_cost(name: str, usd: float) -> None:
    costs = json.loads(COSTS.read_text(encoding="utf-8")) if COSTS.exists() else {}
    costs[name] = round(usd, 4)
    COSTS.write_text(json.dumps(costs, indent=2, sort_keys=True), encoding="utf-8")


async def run() -> None:
    pages = load_pages()
    run_id = corpus_run_id(pages)
    sources = corpus_sources()
    async with eval_deps("eval.systems") as base:
        await ensure_indexed(base, corpus_passages(pages, run_id), run_id)
        for set_name, (file, variants) in SETS.items():
            questions = load_questions(file)
            for variant in variants:
                kind, overrides = VARIANTS[variant]
                deps = replace(base, settings=base.settings.model_copy(update=overrides))
                before = base.ledger.spent
                if kind == "baseline":
                    one = lambda q, d=deps: run_baseline(d, run_id, q)  # noqa: E731
                else:
                    one = lambda q, d=deps: run_pipeline(d, run_id, sources, q)  # noqa: E731
                path = runs_path(set_name, variant)
                ran = await run_all(path, questions, one)
                spent = base.ledger.spent - before
                if ran == len(questions):  # a partial rerun would understate the cost
                    record_cost(path.stem, spent)
                print(f"systems: {path.stem}: ran {ran} of {len(questions)} (${spent:.2f})")
