import asyncio

import pytest

from evidentia.cost import BudgetExceeded, Ledger
from evidentia.schemas import SearchHit
from evidentia.search import Searcher, interleave, url_key
from evidentia.tracing import NoopTracer


def hit(url: str, query: str = "q") -> SearchHit:
    return SearchHit(url=url, query=query)


def test_url_key_ignores_case_of_host_fragment_and_trailing_slash() -> None:
    assert url_key("https://Example.org/a/") == url_key("http://example.org/a#top")
    assert url_key("https://example.org/a?x=1") != url_key("https://example.org/a?x=2")


def test_interleave_takes_one_from_each_query_in_turn() -> None:
    first = [hit("https://a.org/1"), hit("https://a.org/2"), hit("https://a.org/3")]
    second = [hit("https://b.org/1"), hit("https://b.org/2")]
    urls = [h.url for h in interleave([first, second], limit=4)]
    assert urls == ["https://a.org/1", "https://b.org/1", "https://a.org/2", "https://b.org/2"]


def test_interleave_drops_repeats_and_non_web_addresses() -> None:
    first = [hit("https://a.org/1"), hit("ftp://a.org/file")]
    second = [hit("https://a.org/1/"), hit("https://b.org/1")]
    assert [h.url for h in interleave([first, second], 10)] == [
        "https://a.org/1",
        "https://b.org/1",
    ]


class FakeTavily:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def search(self, query: str, **kwargs) -> dict:
        self.calls.append({"query": query, **kwargs})
        slug = query.replace(" ", "-")
        return {"results": [{"url": f"https://{slug}.org/{i}", "title": "T"} for i in range(3)]}


def test_search_charges_each_query_and_uses_basic_depth(settings) -> None:
    ledger, client = Ledger(cap_usd=1.0), FakeTavily()
    searcher = Searcher(settings, ledger, NoopTracer(), client=client)
    hits = asyncio.run(searcher.search("search", ["solar power", "wind power"]))
    assert len(hits) == 6
    assert all(c["search_depth"] == "basic" and c["max_results"] == 6 for c in client.calls)
    assert [c.node for c in ledger.charges] == ["search", "search"]
    assert ledger.spent == pytest.approx(0.016)


def test_search_stops_before_passing_the_cap(settings) -> None:
    ledger, client = Ledger(cap_usd=0.010), FakeTavily()
    searcher = Searcher(settings, ledger, NoopTracer(), client=client)
    with pytest.raises(BudgetExceeded):
        asyncio.run(searcher.search("search", ["one", "two"]))
    assert len(client.calls) == 1
