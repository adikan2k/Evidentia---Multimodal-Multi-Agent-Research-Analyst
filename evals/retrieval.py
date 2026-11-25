"""Retrieval evaluation: keyword vs dense vs hybrid vs hybrid + rerank on the frozen corpus."""

import asyncio
import hashlib

from evals.common import Question, eval_deps, load_pages, load_questions, write_result
from evals.stats import (
    ndcg_at_k,
    paired_difference,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    summary,
)
from evidentia.chunk import make_passages
from evidentia.graph import Deps
from evidentia.schemas import Passage, Source

RETRIEVERS = ["bm25", "dense", "hybrid", "dense_rerank", "hybrid_rerank"]
# (before, after): each pair is reported as the per-question difference after minus before.
COMPARISONS = [
    ("bm25", "dense"),
    ("dense", "hybrid"),
    ("hybrid", "hybrid_rerank"),
    ("dense", "hybrid_rerank"),
    ("dense_rerank", "hybrid_rerank"),
]
# The paired differences keep to these three; the table also has recall and precision at each k.
METRICS = ["recall_at_10", "mrr_at_10", "ndcg_at_10"]
TOP_K = 10
KS = [1, 3, 5, 10]
TABLE = [
    *(f"recall_at_{k}" for k in KS),
    *(f"precision_at_{k}" for k in KS),
    "mrr_at_10",
    "ndcg_at_10",
]


def corpus_run_id(pages: dict[str, dict]) -> str:
    """Changes whenever any page's text changes, so a stale index is never reused."""
    digest = hashlib.sha256("".join(sorted(p["sha256"] for p in pages.values())).encode())
    return f"eval-corpus-{digest.hexdigest()[:12]}"


def corpus_passages(pages: dict[str, dict], run_id: str) -> list[Passage]:
    sources = [Source(id=p["id"], url=p["url"], text=p["text"]) for p in pages.values()]
    return [passage for source in sources for passage in make_passages(source, run_id)]


async def ensure_indexed(deps: Deps, passages: list[Passage], run_id: str) -> None:
    if await deps.store.count(run_id) == len(passages):
        print(f"index: {len(passages)} passages already stored for {run_id}")
        return
    vectors = await deps.embedder.embed_documents("eval-index", [p.text for p in passages])
    await deps.store.ensure_collection()
    await deps.store.upsert(run_id, passages, vectors)
    print(f"index: stored {len(passages)} passages for {run_id}")


def relevant_ids(question: Question, passages: list[Passage]) -> set[str]:
    """A passage is relevant if it overlaps a gold snippet on the same page."""
    return {
        p.id
        for p in passages
        for gold in question.gold
        if p.source_id == gold.page and p.start < gold.end and gold.start < p.end
    }


async def retrieve(deps: Deps, run_id: str, name: str, question: str, vector: list[float]):
    limit = deps.settings.retrieve_limit
    if name in ("bm25", "dense"):
        return await deps.store.single(run_id, question, vector, TOP_K, using=name)
    if name == "dense_rerank":
        candidates = await deps.store.single(run_id, question, vector, limit, using="dense")
        return await deps.embedder.rerank("eval-retrieve", question, candidates, TOP_K)
    candidates = await deps.store.hybrid(run_id, question, vector, limit)
    if name == "hybrid":
        return candidates[:TOP_K]
    return await deps.embedder.rerank("eval-retrieve", question, candidates, TOP_K)


def score(ranked: list[Passage], relevant: set[str]) -> dict[str, float]:
    hits = [p.id in relevant for p in ranked]
    scores = {f"recall_at_{k}": recall_at_k(hits, len(relevant), k) for k in KS}
    scores |= {f"precision_at_{k}": precision_at_k(hits, k) for k in KS}
    return scores | {
        "mrr_at_10": reciprocal_rank(hits, TOP_K),
        "ndcg_at_10": ndcg_at_k(hits, len(relevant), TOP_K),
        "hits": hits,  # the top 10 in order, True where relevant: every score above comes from this
    }


async def evaluate(deps: Deps, run_id: str, question: Question, passages: list[Passage]) -> dict:
    relevant = relevant_ids(question, passages)
    vector = await deps.embedder.embed_query("eval-retrieve", question.question)
    row = {"id": question.id, "kind": question.kind, "relevant_passages": len(relevant)}
    for name in RETRIEVERS:
        ranked = await retrieve(deps, run_id, name, question.question, vector)
        row[name] = score(ranked, relevant)
    return row


def summarise(rows: list[dict]) -> dict:
    table = {
        name: {m: summary([row[name][m] for row in rows]) for m in TABLE} for name in RETRIEVERS
    }
    steps = {
        f"{after}_minus_{before}": {
            m: paired_difference([r[after][m] for r in rows], [r[before][m] for r in rows])
            for m in METRICS
        }
        for before, after in COMPARISONS
    }
    relevant = summary([row["relevant_passages"] for row in rows])
    return {"retrievers": table, "paired_differences": steps, "relevant_per_question": relevant}


async def run() -> None:
    pages, questions = load_pages(), load_questions()
    run_id = corpus_run_id(pages)
    passages = corpus_passages(pages, run_id)
    async with eval_deps("eval.retrieval") as deps:
        await ensure_indexed(deps, passages, run_id)
        limit = asyncio.Semaphore(4)

        async def one(question: Question) -> dict:
            async with limit:
                return await evaluate(deps, run_id, question, passages)

        rows = await asyncio.gather(*(one(q) for q in questions))
        spent = deps.ledger.spent
    worst = sorted(rows, key=lambda r: r["hybrid_rerank"]["recall_at_10"])[:8]
    path = write_result(
        "retrieval",
        {
            "what": "Top-10 passage retrieval on the frozen corpus. The plan asked for four "
            "retrievers; dense_rerank was added to show what keyword search contributes.",
            "gold": "Gold snippets were drafted by Claude from each question's pages and "
            "checked word for word against the page text. See evals/questions.jsonl.",
            "relevance": "A passage is relevant if it overlaps a gold snippet on the same page.",
            "corpus": {"pages": len(pages), "passages": len(passages), "run_id": run_id},
            "questions": len(rows),
            "embed_model": deps.settings.embed_model,
            "rerank_model": deps.settings.rerank_model,
            "interval": "95% bootstrap over questions, 2000 resamples",
            **summarise(rows),
            "lowest_recall_questions": [
                {"id": r["id"], "recall_at_10": r["hybrid_rerank"]["recall_at_10"]} for r in worst
            ],
            "per_question": rows,
            "cost_usd": round(spent, 4),
        },
    )
    print(f"retrieval: wrote {path} (cost ${spent:.2f})")
