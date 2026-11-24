import io
import json

from rich.console import Console

from evidentia.cost import Charge, Ledger
from evidentia.report import Reporter, describe, to_json
from evidentia.schemas import (
    CheckedClaim,
    Passage,
    Repair,
    RunState,
    SearchHit,
    SkippedPage,
    Source,
)

SOURCE = Source(id="S1", url="https://a.org/x", title="A", text="Solar capacity grew 24% in 2023.")
QUOTE = "Solar capacity grew 24% in 2023."
SUPPORTED = CheckedClaim(
    text="Solar grew 24% [in 2023].",
    quote=QUOTE,
    source_id="S1",
    quote_found=True,
    verdict="supported",
    url=SOURCE.url,
    start=0,
    end=32,
)
PARTIAL = CheckedClaim(
    text="Solar grew 24%, more than wind.",
    quote=QUOTE,
    source_id="S1",
    quote_found=True,
    verdict="partial",
    reason="The quote does not mention wind.",
    url=SOURCE.url,
    revised=True,
)
UNVERIFIED = CheckedClaim(
    text="Wind fell.",
    quote="Wind capacity fell sharply.",
    source_id="S1",
    quote_found=False,
    reason="quote is not an exact span of the source",
    url=SOURCE.url,
)
PENDING = CheckedClaim(text="New.", quote="q", source_id="S1", revised=True)
ALL = [SUPPORTED, PARTIAL, UNVERIFIED]


def make_state(**fields) -> RunState:
    return RunState(run_id="r1", question="How fast did solar grow?", **fields)


def make_ledger() -> Ledger:
    ledger = Ledger(1.0)
    ledger.add(Charge(node="plan", item="m", input_tokens=1200, output_tokens=300, usd=0.0054))
    ledger.add(Charge(node="search", item="tavily-basic", usd=0.008))
    return ledger


def render(state: RunState, ledger: Ledger) -> str:
    out = io.StringIO()
    Reporter(Console(file=out, width=200, color_system=None)).final(state, ledger)
    return out.getvalue()


def test_each_node_gets_a_plain_sentence() -> None:
    passage = Passage(id="p", source_id="S1", url="u", start=0, end=1, text="x")
    skipped = [
        SkippedPage(url="u1", reason="disallowed by robots.txt"),
        SkippedPage(url="u2", reason="disallowed by robots.txt"),
        SkippedPage(url="u3", reason="HTTP 403"),
    ]
    hits = [SearchHit(url="https://a.org/1"), SearchHit(url="https://a.org/2")]
    repairs = [Repair(index=2, query="wind capacity", passages=[passage, passage])]
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
    assert describe("write", {"claims": ALL}) == "wrote 3 claims"
    assert describe("quote_check", {"checked": ALL}) == "2 of 3 quotes found word for word"
    assert describe("check", {"checked": ALL}) == "1 supported, 1 partial, 1 unverified"
    assert describe("rewrite", {"repairs": repairs}) == "1 claim failed; wrote a new query for each"
    assert describe("rewrite", {"repairs": []}) == "no claim failed; tightening partial claims only"
    assert describe("reretrieve", {"repairs": repairs}) == (
        "searched the fetched pages again, 2 passages to re-read"
    )
    assert describe("revise", {"checked": [*ALL, PENDING]}) == ("rewrote 1 claim")


def test_final_report_shows_label_quote_reason_source_and_cost() -> None:
    state = make_state(sources=[SOURCE], checked=ALL, trace_url="https://t/1")
    text = render(state, make_ledger())
    assert "1 supported, 1 partial, 1 unverified" in text
    assert "SUPPORTED  Solar grew 24% [in 2023]." in text  # square brackets survive
    assert f'"{QUOTE}"' in text
    assert "PARTIAL  Solar grew 24%, more than wind." in text
    assert "Why partial: The quote does not mention wind." in text
    assert "Rewritten after failing the first check" in text
    assert "UNVERIFIED  Wind fell." in text
    assert "Why unverified: quote is not an exact span of the source" in text
    assert "https://a.org/x" in text
    assert "0.0134" in text and "Cap per run: $1.00" in text
    assert "Trace: https://t/1" in text
    assert "shown only the claim and the quote" in text


def test_supported_claims_show_no_reason_line() -> None:
    text = render(make_state(sources=[SOURCE], checked=[SUPPORTED]), make_ledger())
    assert "Why" not in text and "Rewritten" not in text


def test_empty_run_says_why() -> None:
    assert "No page could be read" in render(make_state(), make_ledger())
    assert "did not support any claim" in render(make_state(sources=[SOURCE]), make_ledger())


def test_progress_lines_list_the_queries() -> None:
    out = io.StringIO()
    reporter = Reporter(Console(file=out, width=120, color_system=None))
    reporter.on_update("plan", {"queries": ["solar growth 2023", "solar capacity record"]})
    reporter.on_update("rewrite", {"repairs": [Repair(index=0, query="wind capacity 2023")]})
    text = out.getvalue()
    assert "plan" in text and "wrote 2 search queries" in text
    assert "solar growth 2023" in text and "solar capacity record" in text
    assert "wind capacity 2023" in text


def test_json_output_has_labels_reasons_costs_and_no_page_text() -> None:
    state = make_state(sources=[SOURCE], checked=ALL, queries=["q"], round=1)
    result = json.loads(to_json(state, make_ledger()))
    assert [c["label"] for c in result["claims"]] == ["supported", "partial", "unverified"]
    assert result["claims"][1]["reason"] == "The quote does not mention wind."
    assert result["claims"][1]["revised"] is True
    assert result["repair_rounds"] == 1
    assert result["sources"] == [
        {
            "id": "S1",
            "url": SOURCE.url,
            "title": "A",
            "kind": "html",
            "pages_read": None,
            "pages_total": None,
            "chars": 32,
        }
    ]
    assert result["cost"]["total_usd"] == 0.0134
    assert [n["node"] for n in result["cost"]["by_node"]] == ["plan", "search"]


def test_cli_report_names_the_page_of_a_pdf_quote() -> None:
    on_page = SUPPORTED.model_copy(update={"url": "https://a.org/r.pdf", "pages": (4, 5)})
    out = io.StringIO()
    Reporter(Console(file=out, width=200)).final(make_state(checked=[on_page]), make_ledger())
    assert "https://a.org/r.pdf  (pp. 4-5)" in out.getvalue()
