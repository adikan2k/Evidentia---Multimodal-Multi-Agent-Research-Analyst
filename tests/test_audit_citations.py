from evidentia.audit.citations import citations_for, locate, parse_answer

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
