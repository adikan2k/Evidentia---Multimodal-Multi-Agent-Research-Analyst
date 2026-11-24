import pytest

from evidentia.quote_check import check_claims, find_quote
from evidentia.schemas import Claim, Source

TEXT = (
    "Solar capacity grew 24% in 2023, the fastest rate on record.\n"
    "Wind additions were slower. It's the third year in a row that solar led."
)
SOURCE = Source(id="S1", url="https://example.org/energy", text=TEXT)


def check(quote: str, source_id: str = "S1"):
    claim = Claim(text="A claim.", quote=quote, source_id=source_id)
    return check_claims([claim], [SOURCE], min_chars=20)[0]


def test_exact_quote_is_verified_with_offsets() -> None:
    quote = "Solar capacity grew 24% in 2023"
    result = check(quote)
    assert result.status == "verified"
    assert TEXT[result.start : result.end] == quote
    assert result.url == SOURCE.url


def test_extra_whitespace_in_the_quote_is_forgiven() -> None:
    assert check("Solar   capacity grew\n24% in 2023").status == "verified"


def test_quote_may_cross_a_paragraph_break() -> None:
    result = check("the fastest rate on record. Wind additions were slower.")
    assert result.status == "verified"
    assert (
        TEXT[result.start : result.end]
        == "the fastest rate on record.\nWind additions were slower."
    )


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
def test_anything_but_an_exact_span_is_unverified(quote: str) -> None:
    result = check(quote)
    assert result.status == "unverified"
    assert result.reason == "quote is not an exact span of the source"
    assert result.start is None


def test_short_quote_is_unverified_even_if_present() -> None:
    result = check("Solar capacity")
    assert result.status == "unverified"
    assert "shorter than 20" in result.reason


def test_unknown_source_is_unverified() -> None:
    result = check("Solar capacity grew 24% in 2023", source_id="S9")
    assert result.status == "unverified"
    assert result.reason == "cites a source that was not fetched"


def test_quote_from_another_source_does_not_count() -> None:
    other = Source(id="S2", url="https://example.org/other", text="Nothing relevant is said here.")
    claim = Claim(text="A claim.", quote="Solar capacity grew 24% in 2023", source_id="S2")
    assert check_claims([claim], [SOURCE, other], min_chars=20)[0].status == "unverified"


def test_empty_quote_is_not_found() -> None:
    assert find_quote("   ", TEXT) is None
