import pytest

from evidentia.quote_check import check_quotes, find_quote
from evidentia.schemas import CheckedClaim, Source

TEXT = (
    "Solar capacity grew 24% in 2023, the fastest rate on record.\n"
    "Wind additions were slower. It's the third year in a row that solar led."
)
SOURCE = Source(id="S1", url="https://example.org/energy", text=TEXT)


def check(quote: str, source_id: str = "S1") -> CheckedClaim:
    claim = CheckedClaim(text="A claim.", quote=quote, source_id=source_id)
    return check_quotes([claim], [SOURCE], min_chars=20)[0]


def test_exact_quote_is_found_with_offsets() -> None:
    quote = "Solar capacity grew 24% in 2023"
    result = check(quote)
    assert result.quote_found is True
    assert TEXT[result.start : result.end] == quote
    assert result.url == SOURCE.url and result.reason == ""


def test_extra_whitespace_in_the_quote_is_forgiven() -> None:
    assert check("Solar   capacity grew\n24% in 2023").quote_found is True


def test_quote_may_cross_a_paragraph_break() -> None:
    result = check("the fastest rate on record. Wind additions were slower.")
    assert result.quote_found is True
    found = TEXT[result.start : result.end]
    assert found == "the fastest rate on record.\nWind additions were slower."


@pytest.mark.parametrize(
    "quote",
    [
        "Solar capacity grew 25% in 2023",  # one digit changed
        "solar capacity grew 24% in 2023",  # case changed
        "It’s the third year in a row",  # curly apostrophe instead of straight
        "Solar capacity grew ... the fastest rate on record",  # stitched with an ellipsis
        "Solar capacity grew 24% in 2023 the fastest rate",  # comma dropped
    ],
)
def test_anything_but_an_exact_span_is_not_found(quote: str) -> None:
    result = check(quote)
    assert result.quote_found is False
    assert result.reason == "quote is not an exact span of the source"
    assert result.start is None
    assert result.failed is True and result.label == "unverified"


def test_short_quote_is_rejected_even_if_present() -> None:
    result = check("Solar capacity")
    assert result.quote_found is False
    assert "shorter than 20" in result.reason


def test_unknown_source_is_rejected() -> None:
    result = check("Solar capacity grew 24% in 2023", source_id="S9")
    assert result.quote_found is False
    assert result.reason == "cites a source that was not fetched"


def test_quote_from_another_source_does_not_count() -> None:
    other = Source(id="S2", url="https://example.org/other", text="Nothing relevant is said here.")
    claim = CheckedClaim(text="A claim.", quote="Solar capacity grew 24% in 2023", source_id="S2")
    assert check_quotes([claim], [SOURCE, other], min_chars=20)[0].quote_found is False


def test_claims_already_checked_are_left_alone() -> None:
    done = CheckedClaim(
        text="A claim.", quote="not on the page at all", source_id="S1", quote_found=True
    )
    assert check_quotes([done], [SOURCE], min_chars=20) == [done]


def test_empty_quote_is_not_found() -> None:
    assert find_quote("   ", TEXT) is None


@pytest.mark.parametrize(
    ("quote_found", "verdict", "label", "failed"),
    [
        (True, "supported", "supported", False),
        (True, "partial", "partial", False),
        (True, "unsupported", "unverified", True),
        (True, None, "unverified", False),
        (False, None, "unverified", True),
        (None, None, "unverified", False),
    ],
)
def test_final_label_follows_the_decision_table(quote_found, verdict, label, failed) -> None:
    claim = CheckedClaim(
        text="t", quote="q", source_id="S1", quote_found=quote_found, verdict=verdict
    )
    assert claim.label == label
    assert claim.failed is failed
    assert claim.model_dump()["label"] == label
