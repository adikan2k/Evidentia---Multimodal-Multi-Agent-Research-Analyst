"""Split a source's text into passages that remember where they came from."""

import re
import uuid

from evidentia.schemas import Passage, Source

Span = tuple[int, int]

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def paragraph_spans(text: str) -> list[Span]:
    """Start and end offsets of each non-empty line."""
    spans, pos = [], 0
    for line in text.split("\n"):
        if line.strip():
            spans.append((pos, pos + len(line)))
        pos += len(line) + 1
    return spans


def split_long(text: str, span: Span, hard_max: int) -> list[Span]:
    """Break an over-long paragraph at sentence ends, and a still over-long sentence by size."""
    start, end = span
    cuts = [start + m.end() for m in _SENTENCE_END.finditer(text[start:end])]
    pieces = []
    for a, b in zip([start, *cuts], [*cuts, end], strict=True):
        b = a + len(text[a:b].rstrip())
        pieces += [(i, min(i + hard_max, b)) for i in range(a, b, hard_max)]
    return pieces


def chunk_spans(text: str, target: int = 1200, hard_max: int = 1600) -> list[Span]:
    """Pack whole paragraphs into spans of about `target` characters."""
    pieces: list[Span] = []
    for span in paragraph_spans(text):
        too_long = span[1] - span[0] > hard_max
        pieces += split_long(text, span, hard_max) if too_long else [span]

    chunks: list[Span] = []
    for start, end in pieces:
        if chunks and end - chunks[-1][0] <= target:
            chunks[-1] = (chunks[-1][0], end)
        else:
            chunks.append((start, end))
    return chunks


def make_passages(source: Source, run_id: str) -> list[Passage]:
    passages = []
    for start, end in chunk_spans(source.text):
        # A stable id means re-indexing the same run overwrites points instead of duplicating them.
        point_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{source.id}:{start}")
        passages.append(
            Passage(
                id=str(point_id),
                source_id=source.id,
                url=source.url,
                start=start,
                end=end,
                text=source.text[start:end],
            )
        )
    return passages
