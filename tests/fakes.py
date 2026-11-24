"""Stand-ins for the outside world, shared by the pipeline tests. Nothing here uses the network."""

import asyncio
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from evidentia.llm import LLM
from evidentia.schemas import Claim, Draft, Judgement, Plan, RepairQueries, Revision, Tightened


def reply(parsed: Any, stop: str = "end_turn", tokens: tuple[int, int] = (1000, 200)) -> dict:
    """Shape of what LangChain returns for a structured call with include_raw=True."""
    raw = SimpleNamespace(
        usage_metadata={"input_tokens": tokens[0], "output_tokens": tokens[1]},
        response_metadata={"stop_reason": stop},
    )
    return {"raw": raw, "parsed": parsed, "parsing_error": None}


def always_supported(user: str) -> Judgement:
    return Judgement(label="supported", reason="The quote states the claim.")


def never_backed(user: str) -> Revision:
    return Revision(backed=False, text="", quote="", source_id="")


class ScriptedLLM(LLM):
    """The real LLM class with the network call replaced by canned answers.

    `judge` and `revise` receive the user prompt and decide what the model "says". A `judge`
    that returns None plays a checker that refused.
    """

    def __init__(
        self,
        settings,
        ledger,
        queries: list[str],
        claims: list[Claim],
        judge: Callable[[str], Judgement | None] = always_supported,
        revise: Callable[[str], Revision] = never_backed,
        repair_queries: list[str] | None = None,
        tightened: str = "",
    ) -> None:
        super().__init__(settings, ledger)
        self.queries = queries
        self.claims = claims
        self.judge = judge
        self.revise = revise
        self.repair_queries = repair_queries or []
        self.tightened = tightened
        self.calls: list[dict[str, str]] = []

    def calls_for(self, schema: type) -> list[dict[str, str]]:
        return [c for c in self.calls if c["schema"] == schema.__name__]

    async def _call(
        self, model, effort, max_tokens, system, user, schema, config, prefix=None
    ) -> dict:
        user = f"{prefix}\n\n{user}" if prefix else user
        self.calls.append(
            {"schema": schema.__name__, "model": model, "system": system, "user": user}
        )
        await asyncio.sleep(0)  # let other calls start, as a real network call would
        if schema is Plan:
            return reply(Plan(queries=self.queries))
        if schema is Draft:
            return reply(Draft(claims=self.claims))
        if schema is RepairQueries:
            return reply(RepairQueries(queries=self.repair_queries))
        if schema is Revision:
            return reply(self.revise(user))
        if schema is Tightened:
            return reply(Tightened(text=self.tightened))
        judgement = self.judge(user)
        return reply(judgement, stop="end_turn" if judgement else "refusal")


class FakeTavily:
    def __init__(self, urls: list[str]) -> None:
        self.urls = urls

    async def search(self, query: str, **kwargs) -> dict:
        return {"results": [{"url": u, "title": f"Title of {u}"} for u in self.urls]}


class FakeVoyage:
    def __init__(self) -> None:
        self.queries: list[str] = []  # every text embedded as a search query, in order

    async def embed(self, texts, **kwargs):
        if kwargs.get("input_type") == "query":
            self.queries += texts
        return SimpleNamespace(embeddings=[[float(len(t)), 1.0] for t in texts], total_tokens=500)

    async def rerank(self, query, documents, model, top_k):
        results = [SimpleNamespace(index=i, relevance_score=1.0 - i / 100) for i in range(top_k)]
        return SimpleNamespace(results=results[: len(documents)], total_tokens=800)


class MemoryQdrant:
    """Keeps points in a list and returns the ones for the asked run, in insertion order."""

    def __init__(self) -> None:
        self.points: list[Any] = []
        self.created = False
        self.searches: list[str] = []  # "hybrid" or "dense", one per search

    async def collection_exists(self, name: str) -> bool:
        return self.created

    async def create_collection(self, name: str, **kwargs) -> None:
        self.created = True

    async def create_payload_index(self, *args, **kwargs) -> None:
        pass

    async def upsert(self, name: str, points, wait: bool) -> None:
        self.points += points

    async def query_points(self, name: str, limit: int, prefetch=None, query_filter=None, **kw):
        self.searches.append("hybrid" if prefetch else kw["using"])
        only_this_run = prefetch[0].filter if prefetch else query_filter
        run_id = only_this_run.must[0].match.value
        mine = [p for p in self.points if p.payload["run_id"] == run_id]
        found = [SimpleNamespace(id=p.id, score=0.5, payload=p.payload) for p in mine[:limit]]
        return SimpleNamespace(points=found)

    async def delete(self, name: str, points_selector) -> None:
        run_id = points_selector.filter.must[0].match.value
        self.points = [p for p in self.points if p.payload["run_id"] != run_id]

    async def close(self) -> None:
        pass
