import json

from evidentia.cost import Charge, Ledger
from evidentia.events import EventBuilder, claim_view, context_window
from evidentia.schemas import CheckedClaim, Repair, RunState, SearchHit, SkippedPage, Source

LEAD = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
QUOTE = "Solar capacity grew 24% in 2023."
TAIL = " nu xi omicron pi rho sigma tau upsilon phi chi psi omega and more words after"
TEXT = LEAD + QUOTE + TAIL
START, END = len(LEAD), len(LEAD) + len(QUOTE)
SOURCE = Source(id="S1", url="https://www.energy.example.org/report", title="Report", text=TEXT)
SOURCES = {"S1": SOURCE}


def claim(**fields) -> CheckedClaim:
    base = {"text": "Solar grew 24%.", "quote": QUOTE, "source_id": "S1"}
    return CheckedClaim(**(base | fields))


def test_context_is_cut_at_word_boundaries_and_never_overlaps_the_quote() -> None:
    window = context_window(TEXT, START, END, size=20)
    assert window["before"] == "kappa lambda mu "  # "iota" would start mid-word, so it is dropped
    assert window["after"] == " nu xi omicron pi"
    assert TEXT.count(window["before"] + QUOTE + window["after"]) == 1


def test_context_at_the_edges_of_the_text_keeps_everything() -> None:
    window = context_window(TEXT, START, END, size=10_000)
    assert window == {"before": LEAD, "after": TAIL}


def test_a_just_written_claim_has_no_label_and_no_context_yet() -> None:
    view = claim_view(claim(), SOURCES)
    assert view["label"] is None and view["context"] is None
    assert view["host"] == "energy.example.org" and view["title"] == "Report"


def test_a_checked_claim_carries_its_label_reason_and_quote_in_context() -> None:
    checked = claim(quote_found=True, verdict="partial", reason="No year.", start=START, end=END)
    view = claim_view(checked, SOURCES)
    assert view["label"] == "partial" and view["reason"] == "No year."
    assert view["quote"] == QUOTE
    assert view["context"]["before"].endswith("lambda mu ")


def test_a_claim_whose_quote_is_missing_is_unverified_at_once() -> None:
    view = claim_view(claim(quote_found=False, reason="not an exact span"), SOURCES)
    assert view["label"] == "unverified" and view["context"] is None


def test_quote_found_but_not_yet_checked_has_no_label() -> None:
    assert claim_view(claim(quote_found=True, start=START, end=END), SOURCES)["label"] is None


def test_events_never_contain_a_whole_page() -> None:
    long_source = SOURCE.model_copy(update={"text": "word " * 5000 + QUOTE + " word" * 5000})
    start = long_source.text.index(QUOTE)
    builder = EventBuilder(Ledger(1.0))
    builder.node_event("fetch", {"sources": [long_source], "skipped": []})
    checked = claim(quote_found=True, verdict="supported", start=start, end=start + len(QUOTE))
    event = builder.node_event("check", {"checked": [checked]})
    assert len(json.dumps(event)) < 2_500
    assert event["data"]["claims"][0]["quote"] == QUOTE


def test_node_events_carry_a_summary_running_cost_and_what_the_page_needs() -> None:
    ledger = Ledger(1.0)
    builder = EventBuilder(ledger)
    plan = builder.node_event("plan", {"queries": ["solar growth"]})
    assert plan == {
        "node": "plan",
        "summary": "wrote 1 search query",
        "cost_usd": 0.0,
        "data": {"queries": ["solar growth"]},
    }
    ledger.add(Charge(node="search", item="tavily", usd=0.008))
    hits = [SearchHit(url="https://www.a.org/1"), SearchHit(url="https://a.org/2")]
    search = builder.node_event("search", {"hits": hits})
    assert search["data"] == {"hosts": ["a.org"]} and search["cost_usd"] == 0.008
    skipped = [SkippedPage(url="https://b.org/x", reason="HTTP 403")]
    fetch = builder.node_event("fetch", {"sources": [SOURCE], "skipped": skipped})
    assert fetch["data"]["sources"][0] == {
        "id": "S1",
        "url": SOURCE.url,
        "host": "energy.example.org",
        "title": "Report",
        "kind": "html",
        "pages_read": None,
        "pages_total": None,
    }
    assert fetch["data"]["skipped"] == [{"host": "b.org", "reason": "HTTP 403"}]
    rewrite = builder.node_event("rewrite", {"repairs": [Repair(index=0, query="solar 2023")]})
    assert rewrite["data"] == {"repair_queries": ["solar 2023"]}


def test_report_counts_labels_and_costs() -> None:
    ledger = Ledger(1.0)
    ledger.add(Charge(node="write", item="m", usd=0.02))
    builder = EventBuilder(ledger)
    builder.node_event("fetch", {"sources": [SOURCE], "skipped": []})
    checked = [
        claim(quote_found=True, verdict="supported", start=START, end=END),
        claim(quote_found=True, verdict="partial", start=START, end=END),
        claim(quote_found=False),
    ]
    state = RunState(run_id="r", question="How fast?", sources=[SOURCE], checked=checked, round=1)
    report = builder.report(state)
    assert report["labels"] == {"supported": 1, "partial": 1, "unverified": 1}
    assert report["cost"]["total_usd"] == 0.02 and report["cost"]["cap_usd"] == 1.0
    assert report["cost"]["by_node"] == [{"node": "write", "calls": 1, "usd": 0.02}]
    assert report["sources_read"] == 1 and report["repair_rounds"] == 1
    assert "text" not in json.dumps(report["cost"]) and TEXT not in json.dumps(report)


PDF = Source(
    id="S2",
    url="https://agency.example.org/report.pdf",
    title="Annual report",
    text="Page one text.\nSolar capacity grew 24% in 2023 on page two.",
    kind="pdf",
    page_starts=[0, 15],
    pages_total=60,
)


def test_a_pdf_claim_carries_its_kind_and_pages() -> None:
    checked = claim(
        source_id="S2", quote_found=True, verdict="supported", start=15, end=47, pages=(2, 2)
    )
    view = claim_view(checked, {"S2": PDF})
    assert view["kind"] == "pdf" and view["pages"] == [2, 2]


def test_a_web_claim_has_no_pages() -> None:
    view = claim_view(claim(quote_found=True, verdict="supported", start=START, end=END), SOURCES)
    assert view["kind"] == "html" and view["pages"] is None


def test_fetch_event_says_how_much_of_a_pdf_was_read() -> None:
    builder = EventBuilder(Ledger(1.0))
    event = builder.node_event("fetch", {"sources": [SOURCE, PDF], "skipped": []})
    pdf = event["data"]["sources"][1]
    assert (pdf["kind"], pdf["pages_read"], pdf["pages_total"]) == ("pdf", 2, 60)
    assert event["data"]["sources"][0]["pages_read"] is None
    assert event["summary"] == "read 2 pages (1 PDF)"


def test_a_pdf_quote_keeps_its_context_on_its_own_page() -> None:
    cover = "Cover page words that belong to page one only."
    body = "The deficit grows from $1.6 trillion in 2024 to $2.6 trillion in 2034 as projected."
    text = cover + "\n" + body + "\nPage three starts here."
    pdf = Source(
        id="S3",
        url="https://a.org/r.pdf",
        text=text,
        kind="pdf",
        page_starts=[0, len(cover) + 1, len(cover) + len(body) + 2],
    )
    start = text.index("$1.6")
    end = start + len("$1.6 trillion in 2024")
    checked = claim(
        source_id="S3", quote_found=True, verdict="supported", start=start, end=end, pages=(2, 2)
    )
    context = claim_view(checked, {"S3": pdf})["context"]
    assert context["before"] == "The deficit grows from "
    assert context["after"] == " to $2.6 trillion in 2034 as projected."
