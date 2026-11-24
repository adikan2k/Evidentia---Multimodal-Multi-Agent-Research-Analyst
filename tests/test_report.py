import io
import json

from rich.console import Console

from evidentia.cost import Charge, Ledger
from evidentia.report import Reporter, describe, to_json
from evidentia.schemas import CheckedClaim, Passage, RunState, SearchHit, SkippedPage, Source

SOURCE = Source(id="S1", url="https://a.org/x", title="A", text="Solar capacity grew 24% in 2023.")
VERIFIED = CheckedClaim(
    text="Solar grew 24% [in 2023].",
    quote="Solar capacity grew 24% in 2023.",
    source_id="S1",
    status="verified",
    url=SOURCE.url,
    start=0,
    end=32,
)
UNVERIFIED = CheckedClaim(
    text="Wind fell.",
    quote="Wind capacity fell sharply.",
    source_id="S1",
    status="unverified",
    reason="quote is not an exact span of the source",
    url=SOURCE.url,
)


def make_state(**fields) -> RunState:
    return RunState(run_id="r1", question="How fast did solar grow?", **fields)


def make_ledger() -> Ledger:
    ledger = Ledger(1.0)
    ledger.add(Charge(node="plan", item="m", input_tokens=1200, output_tokens=300, usd=0.0054))
    ledger.add(Charge(node="search", item="tavily-basic", usd=0.008))
    return ledger


def render(state: RunState, ledger: Ledger) -> str:
    out = io.StringIO()
    Reporter(Console(file=out, width=120, color_system=None)).final(state, ledger)
    return out.getvalue()


def test_each_node_gets_a_plain_sentence() -> None:
    passage = Passage(id="p", source_id="S1", url="u", start=0, end=1, text="x")
    skipped = [
        SkippedPage(url="u1", reason="disallowed by robots.txt"),
        SkippedPage(url="u2", reason="disallowed by robots.txt"),
        SkippedPage(url="u3", reason="HTTP 403"),
    ]
    hits = [SearchHit(url="https://a.org/1"), SearchHit(url="https://a.org/2")]
    assert describe("plan", {"queries": ["a"]}) == "wrote 1 search query"
    assert describe("plan", {"queries": ["a", "b"]}) == "wrote 2 search queries"
    assert describe("search", {"hits": hits}) == "found 2 pages on 1 site"
    assert describe("fetch", {"sources": [SOURCE], "skipped": []}) == "read 1 page"
    assert describe("fetch", {"sources": [SOURCE], "skipped": skipped}) == (
        "read 1 page, skipped 3 (2 disallowed by robots.txt, 1 HTTP 403)"
    )
    assert describe("index", {"passages_indexed": 40}) == "indexed 40 passages (dense + BM25)"
    assert describe("retrieve", {"passages": [passage]}) == (
        "kept the best 1 passage after reranking"
    )
    assert describe("write", {"claims": [VERIFIED, UNVERIFIED]}) == "wrote 2 claims"
    assert describe("quote_check", {"checked": [VERIFIED, UNVERIFIED]}) == (
        "1 verified, 1 unverified"
    )


def test_final_report_shows_status_quote_source_reason_and_cost() -> None:
    state = make_state(sources=[SOURCE], checked=[VERIFIED, UNVERIFIED], trace_url="https://t/1")
    text = render(state, make_ledger())
    assert "VERIFIED  Solar grew 24% [in 2023]." in text  # square brackets survive
    assert '"Solar capacity grew 24% in 2023."' in text
    assert "UNVERIFIED  Wind fell." in text
    assert "Why unverified: quote is not an exact span of the source" in text
    assert "https://a.org/x" in text
    assert "0.0134" in text and "Cap per run: $1.00" in text
    assert "Trace: https://t/1" in text
    assert "not checked yet" in text


def test_empty_run_says_why() -> None:
    assert "No page could be read" in render(make_state(), make_ledger())
    assert "did not support any claim" in render(make_state(sources=[SOURCE]), make_ledger())


def test_progress_line_lists_the_queries() -> None:
    out = io.StringIO()
    reporter = Reporter(Console(file=out, width=120, color_system=None))
    reporter.on_update("plan", {"queries": ["solar growth 2023", "solar capacity record"]})
    text = out.getvalue()
    assert "plan" in text and "wrote 2 search queries" in text
    assert "solar growth 2023" in text and "solar capacity record" in text


def test_json_output_has_claims_costs_and_no_page_text() -> None:
    state = make_state(sources=[SOURCE], checked=[VERIFIED, UNVERIFIED], queries=["q"])
    result = json.loads(to_json(state, make_ledger()))
    assert [c["status"] for c in result["claims"]] == ["verified", "unverified"]
    assert result["sources"] == [{"id": "S1", "url": SOURCE.url, "title": "A", "chars": 32}]
    assert result["cost"]["total_usd"] == 0.0134
    assert [n["node"] for n in result["cost"]["by_node"]] == ["plan", "search"]
