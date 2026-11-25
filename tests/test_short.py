"""The short-page reading's bookkeeping (D-047), with made-up audits. No network, no models."""

from evals.realworld import counts
from evals.reread import OLD_TOO_LITTLE_TEXT, gained, stranded, with_new_pages
from evidentia.audit.graph import TOO_LITTLE_TEXT
from evidentia.schemas import Source

SHORT = "https://short.example/a"
GONE = "https://gone.example/b"
READ = "https://read.example/c"


def page(url: str, label: str, skipped: str | None = None) -> dict:
    return {"url": url, "citation_id": "c1", "label": label, "skipped": skipped}


def claim(label: str, *pages: dict) -> dict:
    ids = [p["citation_id"] for p in pages]
    return {
        "claim": "x",
        "label": label,
        "citation_ids": ids,
        "cited_by": "sentence",
        "pages": pages,
    }


def report() -> dict:
    return {
        "claims": [
            claim("unchecked", page(SHORT, "unchecked", OLD_TOO_LITTLE_TEXT)),  # saved wording
            claim("unchecked", page(GONE, "unchecked", TOO_LITTLE_TEXT)),  # new wording
            claim("supported", page(READ, "supported")),
            claim("unchecked", page(READ, "unchecked", "HTTP 403")),
        ],
        "scorecard": {"pages_cited": 3, "pages_read": 1, "usd": 0.0},
    }


def test_only_stranded_pairs_with_text_now_in_hand_are_judged() -> None:
    sources = {SHORT: Source(id="", url=SHORT, text="a short page " * 40)}
    pairs = stranded(report(), sources)
    assert [(i, p["url"]) for i, p in pairs] == [(0, SHORT)]  # not the page we could not fetch


def test_the_third_reading_changes_only_the_stranded_claims() -> None:
    before = report()
    after = with_new_pages(before, {(0, SHORT): page(SHORT, "not_found")}, read=1)
    assert [c["label"] for c in after["claims"]] == [
        "not_found",
        "unchecked",
        "supported",
        "unchecked",
    ]
    assert gained(before, after) == {"unchecked -> not_found": 1}
    was, now = counts(before), counts(after)
    assert (was["verdict_own"], was["failed_own"]) == (1, 0)
    assert (now["verdict_own"], now["failed_own"]) == (2, 1)
