"""The /audits endpoint (D-041), through real HTTP handling with every outside service faked."""

import httpx
import pytest

from evidentia.api import Services, create_app
from evidentia.audit.events import AuditEventBuilder
from evidentia.audit.graph import PATH
from evidentia.cost import Ledger
from tests.test_api import events
from tests.test_audit_graph import ANSWER, FACT, INJECTION, LONG, make_deps

SHORT = "Solar capacity grew 24% in 2023 [1]. Nuclear output was flat.\n[1] https://energy.example.org/report"


class AuditHarness:
    def __init__(self, settings) -> None:
        self.settings = settings
        services = Services(
            settings=settings,
            tracer=make_deps(settings)[0].tracer,
            make_deps=lambda ledger: None,
            make_llm=lambda ledger: None,
            make_audit_deps=self.make_audit_deps,
        )
        self.app = create_app(services)
        self.limits = self.app.state.limits
        self.ledgers: list[Ledger] = []

    def make_audit_deps(self, ledger: Ledger):
        deps, _ = make_deps(self.settings)
        deps.ledger = ledger
        deps.llm.ledger = ledger
        deps.embedder.ledger = ledger
        self.ledgers.append(ledger)
        return deps

    def audit(self, answer: str = SHORT, ip: str = "203.0.113.5") -> httpx.Response:
        import asyncio

        async def go() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
                headers = {"x-forwarded-for": f"1.2.3.4, {ip}"}
                return await client.post("/audits", json={"answer": answer}, headers=headers)

        return asyncio.run(go())


def test_status_says_live_audits_are_available(settings) -> None:
    api = AuditHarness(settings)
    import asyncio

    async def go():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
            return (await client.get("/status")).json()

    assert asyncio.run(go())["audit_available"] is True


def test_an_audit_streams_each_step_then_the_report(settings) -> None:
    api = AuditHarness(settings)
    response = api.audit()
    assert response.status_code == 200
    stream = events(response)
    nodes = [data["node"] for name, data in stream if name == "node"]
    assert sorted(nodes) == sorted(PATH) and nodes[-1] == "combine"
    name, report = stream[-1]
    assert name == "report"
    assert [c["label"] for c in report["claims"]] == ["supported", "uncited"]
    assert report["scorecard"]["claims"] == 2


def test_claims_carry_their_place_in_the_answer_and_quotes_in_context(settings) -> None:
    api = AuditHarness(settings)
    stream = events(api.audit())
    parse = next(d for n, d in stream if n == "node" and d["node"] == "parse")
    text = parse["data"]["answer_text"]
    report = stream[-1][1]
    for claim in report["claims"]:
        assert text[claim["start"] : claim["end"]] == claim["sentence"]
    page = report["claims"][0]["pages"][0]
    assert page["quotes"][0]["text"] == FACT
    assert page["quotes"][0]["context"]["after"].strip().startswith(INJECTION[:20])
    combine = next(d for n, d in stream if n == "node" and d["node"] == "combine")
    assert [c["label"] for c in combine["data"]["claims"]] == ["supported", "uncited"]


def test_no_fetched_page_text_goes_out_beyond_quotes_and_their_context(settings) -> None:
    api = AuditHarness(settings)
    body = api.audit(f"Solar capacity grew 24% in 2023 [1].\n[1] {LONG}").text
    assert FACT in body  # the quote, word for word
    assert "Paragraph 5." not in body  # far down the page, beyond the context around the quote


def test_each_address_gets_five_live_audits_a_day(settings) -> None:
    api = AuditHarness(settings)
    for _ in range(5):
        assert api.audit().status_code == 200
    refused = api.audit()
    assert refused.status_code == 429 and "5 live audits" in refused.json()["message"]
    assert api.audit(ip="198.51.100.7").status_code == 200


def test_an_audits_cost_is_booked_against_the_daily_budget(settings) -> None:
    api = AuditHarness(settings)
    api.audit()
    assert api.limits.spent == pytest.approx(api.ledgers[0].spent) and api.limits.spent > 0
    assert api.limits.reserved == 0 and not api.limits.auditing


def test_an_audit_that_hits_its_cap_reports_an_error_and_frees_the_slot(settings) -> None:
    settings = settings.model_copy(update={"audit_cap_usd": 0.0001})
    api = AuditHarness(settings)
    name, data = events(api.audit(ANSWER))[-1]
    assert name == "error" and "stopped" in data["message"]
    assert not api.limits.auditing


@pytest.mark.parametrize("answer", ["too short", "x" * 12_001])
def test_answers_must_be_a_sensible_length(settings, answer: str) -> None:
    assert AuditHarness(settings).audit(answer).status_code == 422


def test_audits_stop_when_the_daily_budget_is_used(settings) -> None:
    api = AuditHarness(settings)
    api.limits.spent = settings.daily_budget_usd
    assert api.audit().status_code == 429


def test_the_builder_starts_with_no_pages() -> None:
    assert AuditEventBuilder(Ledger(1.0)).sources == {}
