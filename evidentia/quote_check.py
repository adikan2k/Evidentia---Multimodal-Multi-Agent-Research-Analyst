"""Check quotes with code, not a model: a quote counts only if it is an exact span of the source.

Stored source text is whitespace-clean: single spaces inside a paragraph and one newline between
paragraphs (see `fetch.clean_text`). The only leniency here is whitespace, so a quote that runs
across a paragraph break still matches. Letters, case and punctuation must match exactly.
"""

from evidentia.schemas import CheckedClaim, Source


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


def check_quote(claim: CheckedClaim, sources: dict[str, Source], min_chars: int) -> CheckedClaim:
    def missing(reason: str, url: str = "") -> CheckedClaim:
        return claim.model_copy(update={"quote_found": False, "reason": reason, "url": url})

    source = sources.get(claim.source_id)
    if source is None:
        return missing("cites a source that was not fetched")
    if len(collapse_whitespace(claim.quote)) < min_chars:
        return missing(f"quote is shorter than {min_chars} characters", source.url)
    span = find_quote(claim.quote, source.text)
    if span is None:
        return missing("quote is not an exact span of the source", source.url)
    found = {"quote_found": True, "url": source.url, "start": span[0], "end": span[1]}
    return claim.model_copy(update=found)


def check_quotes(
    claims: list[CheckedClaim], sources: list[Source], min_chars: int
) -> list[CheckedClaim]:
    """Check every claim that has not had its quote checked yet; leave the others alone."""
    by_id = {s.id: s for s in sources}
    return [check_quote(c, by_id, min_chars) if c.quote_found is None else c for c in claims]
