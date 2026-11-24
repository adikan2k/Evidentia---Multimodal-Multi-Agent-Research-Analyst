"""Check quotes with code, not a model: a quote counts only if it is an exact span of the source.

Stored source text is whitespace-clean: single spaces inside a paragraph and one newline between
paragraphs (see `fetch.clean_text`). The only leniency here is whitespace, so a quote that runs
across a paragraph break still matches. Letters, case and punctuation must match exactly.
"""

from evidentia.schemas import CheckedClaim, Claim, Source


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def find_quote(quote: str, source_text: str) -> tuple[int, int] | None:
    """Return the quote's start and end offsets in the source text, or None."""
    needle = collapse_whitespace(quote)
    if not needle:
        return None
    # Swapping each newline for a space keeps every offset the same as in the stored text.
    start = source_text.replace("\n", " ").find(needle)
    return None if start < 0 else (start, start + len(needle))


def check_claim(claim: Claim, sources: dict[str, Source], min_chars: int) -> CheckedClaim:
    def result(status: str, reason: str = "", **extra: object) -> CheckedClaim:
        return CheckedClaim(**claim.model_dump(), status=status, reason=reason, **extra)

    source = sources.get(claim.source_id)
    if source is None:
        return result("unverified", "cites a source that was not fetched")
    if len(collapse_whitespace(claim.quote)) < min_chars:
        return result("unverified", f"quote is shorter than {min_chars} characters", url=source.url)
    span = find_quote(claim.quote, source.text)
    if span is None:
        return result("unverified", "quote is not an exact span of the source", url=source.url)
    return result("verified", url=source.url, start=span[0], end=span[1])


def check_claims(claims: list[Claim], sources: list[Source], min_chars: int) -> list[CheckedClaim]:
    by_id = {s.id: s for s in sources}
    return [check_claim(c, by_id, min_chars) for c in claims]
