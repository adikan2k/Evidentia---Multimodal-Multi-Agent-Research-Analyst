"""Web search through Tavily. We only take URLs from it; pages are fetched by `fetch.py`."""

from itertools import zip_longest
from typing import Any
from urllib.parse import urlsplit

from tavily import AsyncTavilyClient

from evidentia.config import Settings
from evidentia.cost import Charge, Ledger, tavily_usd
from evidentia.schemas import SearchHit
from evidentia.tracing import Tracer

SEARCH_DEPTH = "basic"


def url_key(url: str) -> str:
    """Two URLs with the same key are treated as the same page."""
    parts = urlsplit(url)
    return f"{parts.netloc.lower()}{parts.path.rstrip('/')}?{parts.query}"


def interleave(per_query: list[list[SearchHit]], limit: int) -> list[SearchHit]:
    """Take the top hit of each query, then the second of each, and so on, without repeats.

    This way every query contributes pages before any one query fills the list.
    """
    picked: dict[str, SearchHit] = {}
    for rank in zip_longest(*per_query):
        for hit in rank:
            if hit is not None and hit.url.startswith(("http://", "https://")):
                picked.setdefault(url_key(hit.url), hit)
    return list(picked.values())[:limit]


class Searcher:
    def __init__(
        self, settings: Settings, ledger: Ledger, tracer: Tracer, client: Any = None
    ) -> None:
        self.settings = settings
        self.ledger = ledger
        self.tracer = tracer
        self.client = client or AsyncTavilyClient(
            api_key=settings.tavily_api_key.get_secret_value()
        )

    async def search(self, node: str, queries: list[str]) -> list[SearchHit]:
        per_query = [await self._one(node, query) for query in queries]
        return interleave(per_query, self.settings.max_pages)

    async def _one(self, node: str, query: str) -> list[SearchHit]:
        usd = tavily_usd(SEARCH_DEPTH)
        self.ledger.check(node, usd)
        with self.tracer.span("tavily.search", "tool", {"query": query}) as span:
            response = await self.client.search(
                query, search_depth=SEARCH_DEPTH, max_results=self.settings.results_per_query
            )
            self.ledger.add(Charge(node=node, item=f"tavily-{SEARCH_DEPTH}", usd=usd))
            hits = [
                SearchHit(
                    url=r["url"],
                    title=r.get("title") or "",
                    score=r.get("score") or 0.0,
                    query=query,
                )
                for r in response.get("results", [])
            ]
            span.update(output=[h.url for h in hits], metadata={"usd": usd})
        return hits
