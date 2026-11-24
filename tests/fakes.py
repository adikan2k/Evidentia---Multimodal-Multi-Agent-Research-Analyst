"""Stand-ins for the outside world, shared by the pipeline tests. Nothing here uses the network."""

from types import SimpleNamespace
from typing import Any

from evidentia.llm import LLM
from evidentia.schemas import Claim, Draft, Plan


def reply(parsed: Any, stop: str = "end_turn", tokens: tuple[int, int] = (1000, 200)) -> dict:
    """Shape of what LangChain returns for a structured call with include_raw=True."""
    raw = SimpleNamespace(
        usage_metadata={"input_tokens": tokens[0], "output_tokens": tokens[1]},
        response_metadata={"stop_reason": stop},
    )
    return {"raw": raw, "parsed": parsed, "parsing_error": None}


class ScriptedLLM(LLM):
    """The real LLM class with the network call replaced by canned answers."""

    def __init__(self, settings, ledger, queries: list[str], claims: list[Claim]) -> None:
        super().__init__(settings, ledger)
        self.queries = queries
        self.claims = claims
        self.prompts: dict[str, dict[str, str]] = {}

    async def _call(self, model, effort, max_tokens, system, user, schema, config) -> dict:
        self.prompts[schema.__name__] = {"system": system, "user": user}
        if schema is Plan:
            return reply(Plan(queries=self.queries))
        return reply(Draft(claims=self.claims))


class FakeTavily:
    def __init__(self, urls: list[str]) -> None:
        self.urls = urls

    async def search(self, query: str, **kwargs) -> dict:
        return {"results": [{"url": u, "title": f"Title of {u}"} for u in self.urls]}


class FakeVoyage:
    async def embed(self, texts, **kwargs):
        return SimpleNamespace(embeddings=[[float(len(t)), 1.0] for t in texts], total_tokens=500)

    async def rerank(self, query, documents, model, top_k):
        results = [SimpleNamespace(index=i, relevance_score=1.0 - i / 100) for i in range(top_k)]
        return SimpleNamespace(results=results[: len(documents)], total_tokens=800)


class MemoryQdrant:
    """Keeps points in a list and returns the ones for the asked run, in insertion order."""

    def __init__(self) -> None:
        self.points: list[Any] = []
        self.created = False

    async def collection_exists(self, name: str) -> bool:
        return self.created

    async def create_collection(self, name: str, **kwargs) -> None:
        self.created = True

    async def create_payload_index(self, *args, **kwargs) -> None:
        pass

    async def upsert(self, name: str, points, wait: bool) -> None:
        self.points += points

    async def query_points(self, name: str, prefetch, limit: int, **kwargs):
        run_id = prefetch[0].filter.must[0].match.value
        mine = [p for p in self.points if p.payload["run_id"] == run_id]
        found = [SimpleNamespace(id=p.id, score=0.5, payload=p.payload) for p in mine[:limit]]
        return SimpleNamespace(points=found)

    async def close(self) -> None:
        pass
