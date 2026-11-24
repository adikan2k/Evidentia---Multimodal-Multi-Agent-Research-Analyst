"""Qdrant: one collection, two vectors per passage (dense meaning + BM25 keywords).

The BM25 vector is built by the Qdrant server from the raw text. `models.Document` with the
model name below is sent as is; no embedding model runs on this machine. Confirmed against a
Qdrant 1.20 cloud cluster on 2026-11-24 (the server needs 1.15.3 or newer).
"""

from typing import Any

from qdrant_client import AsyncQdrantClient, models

from evidentia.config import Settings
from evidentia.schemas import Passage
from evidentia.tracing import Tracer

DENSE = "dense"
SPARSE = "bm25"
BM25_MODEL = "Qdrant/bm25"
UPSERT_BATCH = 64


def bm25(text: str) -> models.Document:
    return models.Document(text=text, model=BM25_MODEL)


def run_filter(run_id: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="run_id", match=models.MatchValue(value=run_id))]
    )


def to_point(run_id: str, passage: Passage, vector: list[float]) -> models.PointStruct:
    payload = passage.model_dump(exclude={"id", "score"}) | {"run_id": run_id}
    return models.PointStruct(
        id=passage.id, vector={DENSE: vector, SPARSE: bm25(passage.text)}, payload=payload
    )


def to_passage(point: Any) -> Passage:
    payload = {k: v for k, v in point.payload.items() if k != "run_id"}
    return Passage(id=str(point.id), score=point.score, **payload)


class Store:
    def __init__(self, settings: Settings, tracer: Tracer, client: Any = None) -> None:
        self.settings = settings
        self.tracer = tracer
        self.name = settings.collection
        self.client = client or AsyncQdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=30
        )

    async def aclose(self) -> None:
        await self.client.close()

    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.name):
            return
        await self.client.create_collection(
            self.name,
            vectors_config={
                DENSE: models.VectorParams(
                    size=self.settings.embed_dim, distance=models.Distance.COSINE
                )
            },
            # IDF makes rare words count for more, which is the "inverse document frequency"
            # half of BM25. Qdrant keeps those statistics up to date as points are added.
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        # Every query filters on run_id, so index it.
        await self.client.create_payload_index(
            self.name, "run_id", models.PayloadSchemaType.KEYWORD
        )

    async def upsert(
        self, run_id: str, passages: list[Passage], vectors: list[list[float]]
    ) -> None:
        points = [to_point(run_id, p, v) for p, v in zip(passages, vectors, strict=True)]
        with self.tracer.span("qdrant.upsert", "tool", {"points": len(points)}):
            for i in range(0, len(points), UPSERT_BATCH):
                await self.client.upsert(self.name, points=points[i : i + UPSERT_BATCH], wait=True)

    async def single(
        self, run_id: str, question: str, vector: list[float], limit: int, using: str
    ) -> list[Passage]:
        """One retriever on its own: `using` is "dense" or "bm25". Used by the evals."""
        query = vector if using == DENSE else bm25(question)
        result = await self.client.query_points(
            self.name,
            query=query,
            using=using,
            query_filter=run_filter(run_id),
            limit=limit,
            with_payload=True,
        )
        return [to_passage(p) for p in result.points]

    async def delete_run(self, run_id: str) -> None:
        """Remove a finished run's passages so the free cluster does not fill up."""
        if await self.client.collection_exists(self.name):
            selector = models.FilterSelector(filter=run_filter(run_id))
            await self.client.delete(self.name, points_selector=selector)

    async def count(self, run_id: str) -> int:
        """How many passages are stored for a run."""
        if not await self.client.collection_exists(self.name):
            return 0
        result = await self.client.count(self.name, count_filter=run_filter(run_id), exact=True)
        return result.count

    async def hybrid(
        self, run_id: str, question: str, vector: list[float], limit: int
    ) -> list[Passage]:
        """Top `limit` by meaning and top `limit` by keywords, merged by rank (RRF)."""
        only_this_run = run_filter(run_id)
        with self.tracer.span("qdrant.hybrid", "retriever", {"question": question}) as span:
            result = await self.client.query_points(
                self.name,
                prefetch=[
                    models.Prefetch(query=vector, using=DENSE, limit=limit, filter=only_this_run),
                    models.Prefetch(
                        query=bm25(question), using=SPARSE, limit=limit, filter=only_this_run
                    ),
                ],
                query=models.RrfQuery(rrf=models.Rrf()),
                limit=limit,
                with_payload=True,
            )
            passages = [to_passage(p) for p in result.points]
            span.update(output={"passages": len(passages)})
        return passages
