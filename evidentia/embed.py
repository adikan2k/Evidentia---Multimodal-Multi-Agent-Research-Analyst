"""Voyage embeddings and reranking. No local models: every vector comes from the API."""

from typing import Any

import voyageai

from evidentia.config import Settings
from evidentia.cost import Charge, Ledger, estimate_tokens, voyage_usd
from evidentia.schemas import Passage
from evidentia.tracing import Tracer

# Voyage allows 1,000 texts and 120K tokens per request for voyage-4-large. Stay well inside.
MAX_BATCH_ITEMS = 128
MAX_BATCH_CHARS = 240_000


def batches(texts: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    chars = 0
    for text in texts:
        if out[-1] and (len(out[-1]) >= MAX_BATCH_ITEMS or chars + len(text) > MAX_BATCH_CHARS):
            out.append([])
            chars = 0
        out[-1].append(text)
        chars += len(text)
    return [b for b in out if b]


class Embedder:
    def __init__(
        self, settings: Settings, ledger: Ledger, tracer: Tracer, client: Any = None
    ) -> None:
        self.settings = settings
        self.ledger = ledger
        self.tracer = tracer
        self.client = client or voyageai.AsyncClient(
            api_key=settings.voyage_api_key.get_secret_value(), max_retries=4, timeout=60
        )

    async def embed_documents(self, node: str, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in batches(texts):
            vectors += await self._embed(node, batch, "document")
        return vectors

    async def embed_query(self, node: str, text: str) -> list[float]:
        return (await self._embed(node, [text], "query"))[0]

    async def _embed(self, node: str, texts: list[str], input_type: str) -> list[list[float]]:
        model = self.settings.embed_model
        worst = voyage_usd(model, sum(estimate_tokens(t) for t in texts))
        with (
            self.ledger.reserve(node, worst),
            self.tracer.span("voyage.embed", "embedding", {"texts": len(texts)}) as span,
        ):
            result = await self.client.embed(
                texts, model=model, input_type=input_type, output_dimension=self.settings.embed_dim
            )
            usd = self._charge(node, model, result.total_tokens)
            span.update(metadata={"model": model, "tokens": result.total_tokens, "usd": usd})
        return result.embeddings

    async def rerank(
        self, node: str, query: str, passages: list[Passage], top_k: int
    ) -> list[Passage]:
        """Score each passage against the question and return the best `top_k`, best first."""
        if not passages:
            return []
        model = self.settings.rerank_model
        # Voyage bills the query once per document plus every document.
        worst_tokens = estimate_tokens(query) * len(passages) + sum(
            estimate_tokens(p.text) for p in passages
        )
        with (
            self.ledger.reserve(node, voyage_usd(model, worst_tokens)),
            self.tracer.span("voyage.rerank", "retriever", {"candidates": len(passages)}) as span,
        ):
            result = await self.client.rerank(
                query, [p.text for p in passages], model=model, top_k=top_k
            )
            usd = self._charge(node, model, result.total_tokens)
            span.update(metadata={"model": model, "tokens": result.total_tokens, "usd": usd})
        return [
            passages[r.index].model_copy(update={"score": r.relevance_score})
            for r in result.results
        ]

    def _charge(self, node: str, model: str, tokens: int) -> float:
        usd = voyage_usd(model, tokens)
        self.ledger.add(Charge(node=node, item=model, input_tokens=tokens, usd=usd))
        return usd
