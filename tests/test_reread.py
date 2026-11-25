"""The re-read eval's bookkeeping (D-046), with made-up audits. No network, no models."""

from evals.realworld import counts
from evals.reread import RETRY, gained, relabel, thin_pages, with_new_pages
from evidentia.audit.graph import TOO_LITTLE_TEXT
from evidentia.fetch import NO_READABLE_TEXT

THIN = "https://thin.example/a"
READ = "https://read.example/b"
SHUT = "https://shut.example/c"


def page(url: str, label: str, skipped: str | None = None) -> dict:
    return {"url": url, "citation_id": "c1", "label": label, "skipped": skipped}


def claim(label: str, *pages: dict, cited_by: str = "sentence") -> dict:
    ids = [p["citation_id"] for p in pages]
    return {"claim": "x", "label": label, "citation_ids": ids, "cited_by": cited_by, "pages": pages}


def made_up_report() -> dict:
    return {
        "claims": [
            claim("unchecked", page(THIN, "unchecked", TOO_LITTLE_TEXT)),
            claim("supported", page(READ, "supported"), page(THIN, "unchecked", TOO_LITTLE_TEXT)),
            claim("unchecked", page(SHUT, "unchecked", "HTTP 403")),
            claim("uncited"),
        ],
        "scorecard": {"pages_cited": 3, "pages_read": 1, "usd": 0.01},
    }


def test_only_pages_that_answered_with_too_little_text_are_tried_again() -> None:
    assert RETRY == {TOO_LITTLE_TEXT, NO_READABLE_TEXT}
    report = made_up_report()
    report["claims"].append(
        claim("unchecked", page("https://e.example/", "unchecked", NO_READABLE_TEXT))
    )
    assert thin_pages(report) == [THIN, "https://e.example/"]  # each once; the 403 is left alone


def test_a_claims_label_follows_its_pages_by_the_auditors_rule() -> None:
    assert relabel(claim("unchecked", page(THIN, "not_found"))) == "not_found"
    assert relabel(claim("x", page(READ, "supported"), page(THIN, "not_found"))) == "supported"
    assert relabel(claim("x", page(READ, "unchecked"), page(THIN, "not_found"))) == "unchecked"
    assert relabel(claim("uncited")) == "uncited"


def test_only_the_stranded_claims_change_and_the_counts_add_up() -> None:
    before = made_up_report()
    judged = {(0, THIN): page(THIN, "not_found"), (1, THIN): page(THIN, "contradicted")}
    after = with_new_pages(before, judged, read=1)
    assert [c["label"] for c in after["claims"]] == [
        "not_found",
        "supported",
        "unchecked",
        "uncited",
    ]
    assert before["claims"][0]["label"] == "unchecked"  # the saved audit is not touched
    assert gained(before, after) == {"unchecked -> not_found": 1}
    was, now = counts(before), counts(after)
    assert (was["verdict_own"], was["failed_own"], was["unread_own"]) == (1, 0, 2)
    assert (now["verdict_own"], now["failed_own"], now["unread_own"]) == (2, 1, 1)
    assert now["claims"] == was["claims"] and now["pages_read"] == was["pages_read"] + 1
