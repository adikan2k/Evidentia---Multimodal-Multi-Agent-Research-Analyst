from evidentia.chunk import chunk_spans, make_passages, paragraph_spans
from evidentia.schemas import Source

SENTENCE = "The quick brown fox jumps over the lazy dog near the river bank. "
SHORT = "A short paragraph about solar power."
LONG = (SENTENCE * 40).strip()
TEXT = "\n".join([SHORT, LONG, SHORT, "x" * 2000, SHORT])


def test_paragraph_spans_skip_blank_lines() -> None:
    text = "first\n\nsecond line\n"
    assert [text[a:b] for a, b in paragraph_spans(text)] == ["first", "second line"]


def test_small_paragraphs_are_packed_together() -> None:
    text = "\n".join([SHORT] * 5)
    assert chunk_spans(text) == [(0, len(text))]


def test_no_chunk_exceeds_the_hard_limit() -> None:
    spans = chunk_spans(TEXT, target=1200, hard_max=1600)
    assert len(spans) > 3
    assert all(0 < end - start <= 1600 for start, end in spans)


def test_chunks_are_in_order_and_do_not_overlap() -> None:
    spans = chunk_spans(TEXT)
    assert all(a_end <= b_start for (_, a_end), (b_start, _) in zip(spans, spans[1:], strict=False))


def test_chunks_cover_every_non_space_character() -> None:
    covered = "".join(TEXT[a:b] for a, b in chunk_spans(TEXT))
    assert "".join(covered.split()) == "".join(TEXT.split())


def test_long_paragraph_is_cut_at_sentence_ends() -> None:
    spans = chunk_spans(LONG, target=1200, hard_max=1600)
    assert all(LONG[a:b].endswith(".") for a, b in spans)


def test_passage_text_is_an_exact_slice_of_the_source() -> None:
    source = Source(id="S1", url="https://example.org/a", text=TEXT)
    passages = make_passages(source, run_id="run-1")
    assert passages
    assert all(source.text[p.start : p.end] == p.text for p in passages)
    assert all(p.source_id == "S1" and p.url == source.url for p in passages)


def test_passage_ids_are_stable_per_run_and_differ_across_runs() -> None:
    source = Source(id="S1", url="https://example.org/a", text=TEXT)
    first = [p.id for p in make_passages(source, "run-1")]
    assert first == [p.id for p in make_passages(source, "run-1")]
    assert set(first).isdisjoint(p.id for p in make_passages(source, "run-2"))
    assert len(set(first)) == len(first)


def test_empty_text_gives_no_passages() -> None:
    assert make_passages(Source(id="S1", url="u", text=""), "run-1") == []
