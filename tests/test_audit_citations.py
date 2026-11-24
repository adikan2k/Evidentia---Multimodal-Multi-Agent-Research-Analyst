import pytest

from evidentia.audit.citations import (
    attached,
    citations_for,
    locate,
    paragraph_citations,
    parse_answer,
)

IEA = "https://www.iea.org/reports/renewables-2023"
WIKI = "https://en.wikipedia.org/wiki/Solar_power_(disambiguation)"


def cites(answer: str, sentence: str) -> list[str]:
    parsed = parse_answer(answer)
    span = locate(sentence, parsed.text)
    assert span is not None, (sentence, parsed.text)
    urls = {c.id: c.url for c in parsed.citations}
    return [urls[cid] for cid in citations_for(parsed, *span)]


def test_markdown_links_become_their_text_and_count_as_citations() -> None:
    answer = f"Solar grew 24% in 2023 ([IEA]({IEA})). Wind grew less."
    parsed = parse_answer(answer)
    assert parsed.text == "Solar grew 24% in 2023 (IEA). Wind grew less."
    assert cites(answer, "Solar grew 24% in 2023 (IEA).") == [IEA]
    assert cites(answer, "Wind grew less.") == []


def test_numbered_markers_are_matched_to_the_source_list() -> None:
    answer = (
        "Solar grew 24% in 2023.[1] Panel prices fell [2, 3].\n\n"
        f"Sources:\n[1] IEA report {IEA}\n2. {WIKI}\n[3]: https://example.org/prices."
    )
    parsed = parse_answer(answer)
    assert "Sources" not in parsed.text and "http" not in parsed.text
    assert cites(answer, "Solar grew 24% in 2023.") == [IEA]
    assert cites(answer, "Panel prices fell [2, 3].") == [WIKI, "https://example.org/prices"]


def test_a_sentence_copied_without_its_markers_is_still_found() -> None:
    answer = f"Solar grew 24%[1] in 2023[2].\n[1] {IEA}\n[2] {WIKI}"
    assert cites(answer, "Solar grew 24% in 2023.") == [IEA, WIKI]


def test_footnote_markers_and_bare_addresses() -> None:
    answer = f"Solar grew 24% in 2023.[^1] See {WIKI}.\n\n[^1]: {IEA}"
    parsed = parse_answer(answer)
    assert parsed.text == "Solar grew 24% in 2023.[^1] See en.wikipedia.org."
    assert cites(answer, "Solar grew 24% in 2023.") == [IEA]
    assert cites(answer, "See en.wikipedia.org.") == [WIKI]


def test_the_same_address_gets_one_id() -> None:
    parsed = parse_answer(f"A is true ([x]({IEA})). B is true ([y]({IEA}/)).")
    assert len(parsed.citations) == 2  # a trailing slash is a different address
    parsed = parse_answer(f"A is true ([x]({IEA})). B is true ([y]({IEA})).")
    assert [c.id for c in parsed.citations] == ["c1"]
    assert len(parsed.mentions) == 2


def test_a_citation_on_the_next_line_does_not_belong_to_the_sentence() -> None:
    answer = f"Solar grew 24% in 2023.\n- {IEA}"
    assert cites(answer, "Solar grew 24% in 2023.") == []


def test_a_citation_after_the_next_sentence_belongs_to_that_one() -> None:
    answer = f"Solar grew. Wind fell [1].\n[1] {IEA}"
    assert cites(answer, "Solar grew.") == []
    assert cites(answer, "Wind fell [1].") == [IEA]


def test_markdown_marks_and_bullets_are_dropped() -> None:
    parsed = parse_answer("## Summary\n- **Solar** grew `24%`.\n\n\n* Wind   fell.")
    assert parsed.text == "Summary\nSolar grew 24%.\nWind fell."


def test_a_marker_with_no_source_is_noted_not_guessed() -> None:
    parsed = parse_answer(f"Solar grew [4].\n[1] {IEA}")
    assert parsed.mentions == [] and parsed.unknown_markers == ["4"]


def test_a_sentence_that_is_not_in_the_answer_is_not_located() -> None:
    assert locate("Solar grew 42%.", parse_answer("Solar grew 24% [1].").text) is None


def test_a_numbered_list_item_with_a_link_stays_in_the_answer() -> None:
    stsci = "https://www.stsci.edu/news/2026?utm_source=openai"
    nasa = "https://science.nasa.gov/launch/?utm_source=openai"
    answer = (
        f"Webb launched on December 25, 2021. ([science.nasa.gov]({nasa}))\n\n"
        "Three discoveries:\n\n"
        f"1. **A bright early galaxy.** Webb confirmed the galaxy MoM-z14. ([stsci.edu]({stsci}))\n"
        f"2. **Water vapour** was found near PDS 70 [1].\n\n"
        f"Sources:\n[1] {nasa}"
    )
    parsed = parse_answer(answer)
    assert "Webb confirmed the galaxy MoM-z14." in parsed.text
    assert cites(answer, "Webb confirmed the galaxy MoM-z14. (stsci.edu)") == [stsci]
    assert cites(answer, "Water vapour was found near PDS 70 [1].") == [nasa]
    assert "Sources" not in parsed.text and nasa not in parsed.text


def test_a_sentence_without_a_citation_takes_the_one_that_closes_its_paragraph() -> None:
    from evidentia.audit.citations import paragraph_citations

    answer = (
        f"Solar grew fast in 2023. It led all sources [1][2].\n"
        f"Wind grew too.\n[1] {IEA}\n[2] {WIKI}"
    )
    parsed = parse_answer(answer)
    first = locate("Solar grew fast in 2023.", parsed.text)
    assert citations_for(parsed, *first) == []
    assert paragraph_citations(parsed, first[1]) == ["c1", "c2"]
    wind = locate("Wind grew too.", parsed.text)
    assert paragraph_citations(parsed, wind[1]) == []  # nothing closes that paragraph


# D-043: source lists that arrive on one line, and markers with no source. The shapes below are
# written from how chat apps lay out citations; they are not captured pastes.

EVEREST = "https://en.wikipedia.org/wiki/Mount_Everest"
KESSLER = "https://en.wikipedia.org/wiki/Kessler_syndrome"
S1 = "Mount Everest is 8,849 metres tall [1]."
S2 = "The Kessler syndrome was proposed in 1978 [2]."
PLAIN = "It is in the Himalayas."
BODY = f"{S1} {S2}"

SOURCE_LISTS = {
    "one per line": f"{BODY}\n\nSources:\n[1] {EVEREST}\n[2] {KESSLER}",
    "all on the answer's line": f"{BODY} Sources: [1] {EVEREST} [2] {KESSLER}",
    "one line, no heading": f"{BODY}\n[1] {EVEREST} [2] {KESSLER}",
    "one line, dotted numbers": f"{BODY}\nSources: 1. {EVEREST} 2. {KESSLER}",
    "one line, with titles": f"{BODY} References: [1] Mount Everest, Wikipedia {EVEREST} "
    f"[2] Kessler syndrome {KESSLER}",
    "links as titles": f"{BODY}\n\nSources\n1. [Mount Everest - Wikipedia]({EVEREST})\n"
    f"2. [Kessler syndrome]({KESSLER})",
    "footnotes": f"{BODY.replace('[1]', '[^1]').replace('[2]', '[^2]')}\n\n"
    f"[^1]: {EVEREST}\n[^2]: {KESSLER}",
    "windows line ends": f"{BODY}\r\n\r\nCitations:\r\n[1] {EVEREST}\r\n[2] {KESSLER}",
}


@pytest.mark.parametrize("answer", SOURCE_LISTS.values(), ids=SOURCE_LISTS.keys())
def test_each_marker_reaches_its_own_page_however_the_list_is_laid_out(answer: str) -> None:
    parsed = parse_answer(answer)
    urls = {c.id: c.url for c in parsed.citations}
    assert parsed.unresolved == [] and "http" not in parsed.text and "ources" not in parsed.text
    for sentence, url in ((S1, EVEREST), (S2, KESSLER)):
        span = locate(sentence.replace("[", "[^") if "[^" in answer else sentence, parsed.text)
        cited, unread = attached(parsed, *span)
        assert [urls[c] for c in cited] == [url] and unread == []


def test_inline_links_and_linked_markers_need_no_source_list() -> None:
    answer = f"Mount Everest is 8,849 metres tall ([Wikipedia]({EVEREST})). Kessler [2]({KESSLER})."
    parsed = parse_answer(answer)
    assert [c.url for c in parsed.citations] == [EVEREST, KESSLER] and parsed.unresolved == []


def test_a_marker_with_no_source_is_unread_and_borrows_nothing() -> None:
    parsed = parse_answer(f"{S1} {PLAIN} {S2}\n[1] {EVEREST}")
    cited, unread = attached(parsed, *locate(S2, parsed.text))
    assert cited == [] and unread == ["2"]
    plain = locate(PLAIN, parsed.text)
    # The plain sentence is followed by an unreadable marker, so it borrows nothing either.
    assert attached(parsed, *plain) == ([], []) and paragraph_citations(parsed, plain[1]) == []


def test_a_source_list_that_cannot_be_parsed_is_never_borrowed_from() -> None:
    parsed = parse_answer(f"{PLAIN} {S2} Sources: (1) {EVEREST} (2) {KESSLER}")
    plain, kessler = locate(PLAIN, parsed.text), locate(S2, parsed.text)
    assert attached(parsed, *kessler) == ([], ["2"])
    assert paragraph_citations(parsed, plain[1]) == []
    no_markers = parse_answer(f"{PLAIN} Everest is tall. Sources: {EVEREST}")
    assert paragraph_citations(no_markers, locate(PLAIN, no_markers.text)[1]) == []


def test_unnumbered_sources_under_a_heading_leave_the_answer_text() -> None:
    parsed = parse_answer(
        f"{PLAIN} Everest is tall.\n\nSources:\n- {EVEREST}\n- [Kessler]({KESSLER})"
    )
    assert parsed.text == f"{PLAIN} Everest is tall." and parsed.mentions == []


def test_a_sentence_that_mentions_sources_is_not_cut() -> None:
    parsed = parse_answer("Sources: the agency and two universities. Solar grew 24% [1].")
    assert parsed.text.startswith("Sources: the agency")
