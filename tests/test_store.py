import asyncio
from types import SimpleNamespace

from qdrant_client import models

from evidentia.schemas import Passage
from evidentia.store import BM25_MODEL, Store, to_passage, to_point
from evidentia.tracing import NoopTracer

PASSAGE = Passage(
    id="11111111-1111-1111-1111-111111111111",
    source_id="S2",
    url="https://example.org/a",
    start=10,
    end=40,
    text="Solar capacity grew 24% in 2023",
)


class FakeQdrant:
    def __init__(self, exists: bool = False) -> None:
        self.exists = exists
        self.calls: list[tuple[str, dict]] = []

    async def collection_exists(self, name: str) -> bool:
        return self.exists

    async def create_collection(self, name: str, **kwargs) -> None:
        self.calls.append(("create_collection", kwargs))
        self.exists = True

    async def create_payload_index(self, name: str, field: str, schema) -> None:
        self.calls.append(("create_payload_index", {"field": field}))

    async def upsert(self, name: str, points, wait: bool) -> None:
        self.calls.append(("upsert", {"points": points}))

    async def query_points(self, name: str, **kwargs):
        self.calls.append(("query_points", kwargs))
        point = SimpleNamespace(
            id=PASSAGE.id, score=0.5, payload=to_point("run-1", PASSAGE, [0.1]).payload
        )
        return SimpleNamespace(points=[point])


def test_point_carries_both_vectors_and_the_run_id() -> None:
    point = to_point("run-1", PASSAGE, [0.1, 0.2])
    assert point.vector["dense"] == [0.1, 0.2]
    assert point.vector["bm25"] == models.Document(text=PASSAGE.text, model=BM25_MODEL)
    assert point.payload["run_id"] == "run-1"
    assert point.payload["start"] == 10 and point.payload["source_id"] == "S2"


def test_point_round_trips_back_to_the_same_passage() -> None:
    point = to_point("run-1", PASSAGE, [0.1])
    stored = SimpleNamespace(id=point.id, score=0.9, payload=point.payload)
    assert to_passage(stored) == PASSAGE.model_copy(update={"score": 0.9})


def test_collection_is_created_once_with_dense_and_idf_sparse(settings) -> None:
    client = FakeQdrant(exists=False)
    store = Store(settings, NoopTracer(), client=client)
    asyncio.run(store.ensure_collection())
    asyncio.run(store.ensure_collection())
    assert [name for name, _ in client.calls] == ["create_collection", "create_payload_index"]
    created = client.calls[0][1]
    assert created["vectors_config"]["dense"].size == 1024
    assert created["sparse_vectors_config"]["bm25"].modifier == models.Modifier.IDF
    assert client.calls[1][1] == {"field": "run_id"}


def test_upsert_sends_points_in_batches(settings) -> None:
    client = FakeQdrant(exists=True)
    store = Store(settings, NoopTracer(), client=client)
    passages = [PASSAGE.model_copy(update={"id": str(i)}) for i in range(70)]
    asyncio.run(store.upsert("run-1", passages, [[0.1]] * 70))
    assert [len(kwargs["points"]) for _, kwargs in client.calls] == [64, 6]


def test_hybrid_query_fuses_dense_and_bm25_within_one_run(settings) -> None:
    client = FakeQdrant(exists=True)
    store = Store(settings, NoopTracer(), client=client)
    passages = asyncio.run(store.hybrid("run-1", "solar growth", [0.1, 0.2], limit=30))
    query = client.calls[0][1]
    dense, sparse = query["prefetch"]
    assert (dense.using, dense.query, dense.limit) == ("dense", [0.1, 0.2], 30)
    assert sparse.using == "bm25"
    assert sparse.query == models.Document(text="solar growth", model=BM25_MODEL)
    assert isinstance(query["query"], models.RrfQuery)
    for prefetch in (dense, sparse):
        assert prefetch.filter.must[0].key == "run_id"
        assert prefetch.filter.must[0].match.value == "run-1"
    assert passages == [PASSAGE.model_copy(update={"score": 0.5})]
