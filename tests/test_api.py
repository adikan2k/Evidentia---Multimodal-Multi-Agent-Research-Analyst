"""The web API, driven through real HTTP handling with every outside service faked."""

import asyncio
import json
from datetime import date

import httpx
import pytest

from evidentia.api import Services, create_app
from evidentia.cost import Ledger
from evidentia.embed import Embedder
from evidentia.fetch import Fetcher, is_public_host
from evidentia.graph import MAIN_PATH, Deps
from evidentia.limits import Limits, Refused
from evidentia.schemas import Judgement
from evidentia.search import Searcher
from evidentia.store import Store
from evidentia.tracing import NoopTracer
from tests.fakes import FakeTavily, FakeVoyage, MemoryQdrant, ScriptedLLM
from tests.test_graph import BACKED, FACT, GOOD_URL, OFF_TOPIC, handler, judge

QUESTION = "How fast did solar capacity grow in 2023?"


class Harness:
    """An app wired to fakes, remembering the fake database so tests can look inside it."""

    def __init__(self, settings, claims=(BACKED,)) -> None:
        self.settings = settings
        self.qdrant = MemoryQdrant()
        self.claims = list(claims)
        services = Services(
            settings=settings,
            tracer=NoopTracer(),
            make_deps=self.make_deps,
            make_llm=lambda ledger: ScriptedLLM(settings, ledger, [], [], judge=judge),
        )
        self.app = create_app(services)
        self.limits: Limits = self.app.state.limits

    def make_deps(self, ledger: Ledger) -> Deps:
        s, tracer = self.settings, NoopTracer()
        web = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return Deps(
            settings=s,
            ledger=ledger,
            tracer=tracer,
            llm=ScriptedLLM(s, ledger, ["solar growth 2023"], self.claims, judge=judge),
            searcher=Searcher(s, ledger, tracer, client=FakeTavily([GOOD_URL])),
            fetcher=Fetcher(s, tracer, client=web),
            embedder=Embedder(s, ledger, tracer, client=FakeVoyage()),
            store=Store(s, tracer, client=self.qdrant),
        )

    def call(self, method: str, path: str, ip: str = "203.0.113.5", **kwargs) -> httpx.Response:
        async def go() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
                # The first entry is what a visitor could forge; the last is the real address.
                headers = {"x-forwarded-for": f"1.2.3.4, {ip}"} | kwargs.pop("headers", {})
                return await client.request(method, path, headers=headers, **kwargs)

        return asyncio.run(go())

    def run(self, question: str = QUESTION, ip: str = "203.0.113.5") -> httpx.Response:
        return self.call("POST", "/runs", ip=ip, json={"question": question})


def events(response: httpx.Response) -> list[tuple[str, dict]]:
    out = []
    for block in response.text.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_health_and_status(settings) -> None:
    api = Harness(settings)
    assert api.call("GET", "/health").json() == {"ok": True}
    assert api.call("GET", "/status").json() == {"live_available": True, "run_cap_usd": 0.25}


def test_a_run_streams_each_step_then_the_report(settings) -> None:
    api = Harness(settings)
    response = api.run()
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    stream = events(response)
    assert [data["node"] for name, data in stream if name == "node"] == MAIN_PATH
    assert all("t" in data and "summary" in data for name, data in stream if name == "node")
    name, report = stream[-1]
    assert name == "report" and report["question"] == QUESTION
    assert report["labels"] == {"supported": 1, "partial": 0, "unverified": 0}
    assert report["claims"][0]["quote"] == FACT and report["claims"][0]["context"]


def test_the_stream_carries_quotes_with_context_and_no_source_text_field(settings) -> None:
    # The test page is tiny, so its context window covers most of it. That a long page is cut
    # down to a window is tested in test_events.py.
    api = Harness(settings)
    stream = events(api.run())
    assert all("text" not in source for _, data in stream for source in data.get("sources", []))
    fetch = next(data for name, data in stream if name == "node" and data["node"] == "fetch")
    assert set(fetch["data"]["sources"][0]) == {"id", "url", "host", "title"}


def test_after_a_run_its_cost_is_booked_and_its_passages_are_deleted(settings) -> None:
    api = Harness(settings)
    api.run()
    assert 0 < api.limits.spent < 0.25
    assert api.limits.reserved == pytest.approx(0.0) and api.limits.running == set()
    assert api.qdrant.points == []


def test_each_address_gets_three_live_runs_a_day(settings) -> None:
    api = Harness(settings)
    assert [api.run().status_code for _ in range(3)] == [200, 200, 200]
    refused = api.run()
    assert refused.status_code == 429 and "3 live runs" in refused.json()["message"]
    assert api.run(ip="198.51.100.7").status_code == 200  # someone else is unaffected


def test_live_runs_stop_when_the_daily_budget_is_used(settings) -> None:
    api = Harness(settings.model_copy(update={"daily_budget_usd": 0.10}))
    refused = api.run()  # a run reserves 0.12 before it starts
    assert refused.status_code == 429 and "budget" in refused.json()["message"]
    assert api.call("GET", "/status").json()["live_available"] is False


def test_a_run_that_hits_its_cap_reports_an_error_and_frees_the_slot(settings) -> None:
    api = Harness(settings.model_copy(update={"public_run_cap_usd": 0.045}))
    stream = events(api.run())
    name, data = stream[-1]
    assert name == "error" and data["message"].startswith("The run stopped: write")
    assert api.limits.running == set()


@pytest.mark.parametrize("question", ["too short", "x" * 301])
def test_questions_must_be_a_sensible_length(settings, question: str) -> None:
    assert Harness(settings).run(question).status_code == 422


def test_check_returns_the_checkers_verdict_in_the_sites_words(settings) -> None:
    api = Harness(settings)
    backed = api.call("POST", "/check", json={"claim": BACKED.text, "quote": FACT})
    assert backed.json()["label"] == "supported"
    broken = api.call("POST", "/check", json={"claim": OFF_TOPIC.text, "quote": FACT}).json()
    assert broken == {
        "label": "unverified",
        "verdict": "unsupported",
        "reason": "The quote says nothing about cost.",
    }
    assert api.limits.spent > 0


def test_checks_are_limited_per_address(settings) -> None:
    api = Harness(settings.model_copy(update={"max_checks_per_ip": 1}))
    body = {"claim": BACKED.text, "quote": FACT}
    assert api.call("POST", "/check", json=body).status_code == 200
    assert api.call("POST", "/check", json=body).status_code == 429


def test_a_checker_that_refuses_gives_a_clear_error(settings) -> None:
    api = Harness(settings)
    refusing = ScriptedLLM(settings, Ledger(1.0), [], [], judge=lambda user: None)
    services = Services(settings, NoopTracer(), api.make_deps, lambda ledger: refusing)
    app = create_app(services)

    async def go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            return await client.post("/check", json={"claim": BACKED.text, "quote": FACT})

    response = asyncio.run(go())
    assert response.status_code == 502 and "did not return a verdict" in response.json()["message"]


def test_only_the_site_may_call_from_a_browser(settings) -> None:
    api = Harness(settings)
    ours = api.call("GET", "/health", headers={"origin": "http://localhost:3000"})
    theirs = api.call("GET", "/health", headers={"origin": "https://elsewhere.example"})
    assert ours.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in theirs.headers


def test_limits_reset_at_the_start_of_a_new_day(settings) -> None:
    day = [date(2026, 11, 24)]
    limits = Limits(settings, clock=lambda: day[0])
    for _ in range(3):
        limits.start_run("a")
        limits.finish_run("a", 0.05)
    with pytest.raises(Refused):
        limits.start_run("a")
    day[0] = date(2026, 11, 25)
    limits.start_run("a")
    assert limits.spent == 0.0 and limits.runs["a"] == 1


def test_one_run_at_a_time_per_address_and_two_in_total(settings) -> None:
    limits = Limits(settings)
    limits.start_run("a")
    with pytest.raises(Refused, match="already in progress"):
        limits.start_run("a")
    limits.start_run("b")
    with pytest.raises(Refused, match="Other runs"):
        limits.start_run("c")
    limits.finish_run("a", 0.05)
    limits.start_run("c")


def test_runs_in_flight_count_against_the_daily_budget(settings) -> None:
    limits = Limits(
        settings.model_copy(update={"daily_budget_usd": 0.20, "max_concurrent_runs": 9})
    )
    limits.start_run("a")  # reserves 0.12
    with pytest.raises(Refused, match="budget"):
        limits.start_run("b")
    limits.finish_run("a", 0.03)  # the reservation is replaced by the real cost
    limits.start_run("b")


@pytest.mark.parametrize(
    "host",
    ["localhost", "127.0.0.1", "10.0.0.8", "192.168.1.10", "169.254.169.254", "::1"]
    + ["metadata.google.internal", "printer.local", ""],
)
def test_private_and_internal_addresses_are_not_fetched(host: str) -> None:
    assert is_public_host(host) is False


@pytest.mark.parametrize("host", ["example.org", "en.wikipedia.org", "93.184.216.34"])
def test_ordinary_public_addresses_are_fetched(host: str) -> None:
    assert is_public_host(host) is True


def test_a_page_at_a_private_address_is_skipped_without_a_request(settings) -> None:
    seen: list[str] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(404)

    from evidentia.schemas import SearchHit

    fetcher = Fetcher(
        settings, NoopTracer(), client=httpx.AsyncClient(transport=httpx.MockTransport(spy))
    )
    hit = SearchHit(url="http://169.254.169.254/latest/meta-data/")
    _, skipped = asyncio.run(fetcher.fetch_all([hit]))
    assert skipped[0].reason == "not a public address" and seen == []


def test_judge_fake_is_the_one_the_graph_tests_use() -> None:
    assert judge("cheapest").label == "unsupported"
    assert isinstance(judge("anything else"), Judgement)


def test_a_forged_forwarded_address_does_not_dodge_the_per_address_limit(settings) -> None:
    api = Harness(settings)

    def run_claiming_to_be(fake: str) -> int:
        headers = {"x-forwarded-for": f"{fake}, 203.0.113.5"}
        return api.call("POST", "/runs", headers=headers, json={"question": QUESTION}).status_code

    assert [run_claiming_to_be(f"9.9.9.{n}") for n in range(4)] == [200, 200, 200, 429]
