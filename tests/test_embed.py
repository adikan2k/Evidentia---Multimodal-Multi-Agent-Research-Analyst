import asyncio
from types import SimpleNamespace

import pytest

from evidentia.cost import BudgetExceeded, Ledger
from evidentia.embed import MAX_BATCH_ITEMS, Embedder, batches
from evidentia.schemas import Passage
from evidentia.tracing import NoopTracer


class FakeVoyage:
    def __init__(self) -> None:
        self.embed_calls: list[dict] = []

    async def embed(self, texts, **kwargs):
        self.embed_calls.append({"texts": texts, **kwargs})
        return SimpleNamespace(embeddings=[[float(len(t))] for t in texts], total_tokens=1000)

    async def rerank(self, query, documents, model, top_k):
        order = sorted(range(len(documents)), key=lambda i: len(documents[i]), reverse=True)
        results = [SimpleNamespace(index=i, relevance_score=len(documents[i]) / 10) for i in order]
        return SimpleNamespace(results=results[:top_k], total_tokens=2000)


def passage(text: str) -> Passage:
    return Passage(id=text, source_id="S1", url="u", start=0, end=len(text), text=text)


def test_batches_keep_order_and_respect_limits() -> None:
    texts = [f"t{i}" for i in range(MAX_BATCH_ITEMS + 5)]
    out = batches(texts)
    assert [len(b) for b in out] == [MAX_BATCH_ITEMS, 5]
    assert [t for b in out for t in b] == texts
    assert batches([]) == []
    assert [len(b) for b in batches(["x" * 200_000, "y" * 200_000])] == [1, 1]


def test_documents_and_query_use_the_right_input_type(settings) -> None:
    ledger, client = Ledger(1.0), FakeVoyage()
    embedder = Embedder(settings, ledger, NoopTracer(), client=client)
    vectors = asyncio.run(embedder.embed_documents("index", ["aa", "bbbb"]))
    query = asyncio.run(embedder.embed_query("retrieve", "abc"))
    assert vectors == [[2.0], [4.0]] and query == [3.0]
    assert [c["input_type"] for c in client.embed_calls] == ["document", "query"]
    assert all(c["model"] == "voyage-4-large" for c in client.embed_calls)
    assert all(c["output_dimension"] == 1024 for c in client.embed_calls)


def test_embedding_cost_is_recorded_from_actual_tokens(settings) -> None:
    ledger = Ledger(1.0)
    embedder = Embedder(settings, ledger, NoopTracer(), client=FakeVoyage())
    asyncio.run(embedder.embed_documents("index", ["aa"]))
    charge = ledger.charges[0]
    assert (charge.node, charge.item, charge.input_tokens) == ("index", "voyage-4-large", 1000)
    assert charge.usd == pytest.approx(0.00012)


def test_rerank_returns_best_first_with_scores(settings) -> None:
    ledger = Ledger(1.0)
    embedder = Embedder(settings, ledger, NoopTracer(), client=FakeVoyage())
    passages = [passage("short"), passage("the longest passage"), passage("medium one")]
    top = asyncio.run(embedder.rerank("retrieve", "q", passages, top_k=2))
    assert [p.text for p in top] == ["the longest passage", "medium one"]
    assert top[0].score == pytest.approx(1.9)
    assert ledger.charges[0].item == "rerank-3"


def test_rerank_of_nothing_makes_no_call(settings) -> None:
    ledger = Ledger(1.0)
    embedder = Embedder(settings, ledger, NoopTracer(), client=FakeVoyage())
    assert asyncio.run(embedder.rerank("retrieve", "q", [], top_k=5)) == []
    assert ledger.charges == []


def test_embedding_is_blocked_by_the_cap(settings) -> None:
    client = FakeVoyage()
    embedder = Embedder(settings, Ledger(cap_usd=0.0), NoopTracer(), client=client)
    with pytest.raises(BudgetExceeded):
        asyncio.run(embedder.embed_documents("index", ["some text"]))
    assert client.embed_calls == []
