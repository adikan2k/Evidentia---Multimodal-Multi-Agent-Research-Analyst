"""Find the citations in a pasted AI answer, with code (D-037, step 1).

Answers arrive in a few shapes: markdown links (`[IEA](https://...)`), bare addresses, and
numbered markers (`[1]`, `[^2]`, `[1, 3]`) with a numbered source list at the end. This turns
the answer into plain text the splitter can copy sentences from, and records where in that text
each citation sits. Which claim cites which page is decided from those positions, not by a model.
"""

import re

from pydantic import BaseModel

from evidentia.quote_check import collapse_whitespace, find_quote

URL = r"https?://(?:[^\s()<>\[\]]|\([^\s()]*\))+"  # allows one level of (...) as in Wikipedia
TRAILING = ".,;:!?'\""

TOKEN = re.compile(
    rf"\[(?P<label>[^\]\n]*)\]\((?P<link>{URL})\)"
    r"|\[\^?(?P<nums>\d+(?:\s*,\s*\d+)*)\]"
    rf"|(?P<bare>{URL})"
    r"|(?P<emph>\*\*|__|`)"
)
REFERENCE = re.compile(rf"^\s*(?:\[\^?(?P<a>\d+)\]:?|(?P<b>\d+)[.)])\s*(?P<rest>.*?{URL}.*)$")
FIRST_URL = re.compile(URL)
HEADING = re.compile(r"^\s*(?:sources|citations|references)\s*:?\s*$", re.IGNORECASE)
LINE_START = re.compile(r"^\s*(?:#{1,6}\s+|[-*+•]\s+)?")
# What may sit between a sentence and a citation that still belongs to it: "...2023 [1][2]."
GAP = set(" \t.,;:!?()\"'")


class Cited(BaseModel):
    id: str  # "c1", "c2", ... one per distinct address
    url: str


class Mention(BaseModel):
    citation_id: str
    start: int  # where the citation sits in ParsedAnswer.text
    end: int


class ParsedAnswer(BaseModel):
    text: str  # the answer without its source list, links and markdown marks
    citations: list[Cited] = []
    mentions: list[Mention] = []
    unknown_markers: list[str] = []  # markers like [7] with no matching source


def tidy_url(url: str) -> str:
    url = url.rstrip(TRAILING)
    if url.endswith(")") and url.count("(") < url.count(")"):
        url = url[:-1]
    return url


def host_of(url: str) -> str:
    host = url.split("//", 1)[1].split("/", 1)[0]
    return host.removeprefix("www.")


class _Builder:
    """Writes the plain text one piece at a time, keeping single spaces and noting citations."""

    def __init__(self, references: dict[str, str]) -> None:
        self.references = references
        self.text = ""
        self.ids: dict[str, str] = {}
        self.mentions: list[Mention] = []
        self.unknown: list[str] = []

    def plain(self, piece: str) -> None:
        piece = re.sub(r"\s+", " ", piece)
        if piece.startswith(" ") and (not self.text or self.text[-1] in " \n"):
            piece = piece[1:]
        self.text += piece

    def cited(self, piece: str, url: str) -> None:
        url = tidy_url(url)
        cid = self.ids.setdefault(url, f"c{len(self.ids) + 1}")
        start = len(self.text)
        self.plain(piece)
        start = min(start, len(self.text))
        self.mentions.append(Mention(citation_id=cid, start=start, end=len(self.text)))

    def line(self, raw: str) -> None:
        before = len(self.text)
        raw = raw[LINE_START.match(raw).end() :]
        pos = 0
        for m in TOKEN.finditer(raw):
            self.plain(raw[pos : m.start()])
            pos = m.end()
            if m["link"]:
                label = m["label"].strip()
                self.cited(host_of(m["link"]) if label in ("", m["link"]) else label, m["link"])
            elif m["nums"]:
                self.marker(m.group(0), m["nums"])
            elif m["bare"]:
                url = tidy_url(m["bare"])
                self.cited(host_of(url), url)
                self.plain(m["bare"][len(url) :])  # punctuation the address was followed by
        self.plain(raw[pos:])
        self.end_line(before)

    def marker(self, written: str, nums: str) -> None:
        start = len(self.text)
        self.plain(written)
        for n in (part.strip() for part in nums.split(",")):
            url = self.references.get(n)
            if url is None:
                self.unknown.append(n)
                continue
            cid = self.ids.setdefault(url, f"c{len(self.ids) + 1}")
            self.mentions.append(Mention(citation_id=cid, start=start, end=len(self.text)))

    def end_line(self, before: int) -> None:
        self.text = self.text.rstrip(" ")
        if len(self.text) == before:
            return
        self.text += "\n"
        for m in self.mentions:  # a citation at the very end of a line loses no characters
            m.start, m.end = min(m.start, len(self.text) - 1), min(m.end, len(self.text) - 1)


def references_in(lines: list[str]) -> tuple[dict[str, str], set[int]]:
    """Numbered source lines ("[1] Title https://...", "2. https://...") and where they are."""
    references, where = {}, set()
    for i, line in enumerate(lines):
        m = REFERENCE.match(line)
        if m:
            references.setdefault(m["a"] or m["b"], tidy_url(FIRST_URL.search(m["rest"]).group(0)))
            where.add(i)
        elif HEADING.match(line):
            where.add(i)
    return references, where


def parse_answer(answer: str) -> ParsedAnswer:
    lines = answer.replace("\r\n", "\n").split("\n")
    references, reference_lines = references_in(lines)
    builder = _Builder(references)
    for i, line in enumerate(lines):
        if i not in reference_lines:
            builder.line(line)
    citations = [Cited(id=cid, url=url) for url, cid in builder.ids.items()]
    return ParsedAnswer(
        text=builder.text.rstrip("\n"),
        citations=citations,
        mentions=builder.mentions,
        unknown_markers=builder.unknown,
    )


MARKER = re.compile(r"\[\^?\d+(?:\s*,\s*\d+)*\]")


def locate(sentence: str, text: str) -> tuple[int, int] | None:
    """Where the splitter's sentence is in the answer text. Exact, except that numbered markers
    may be left out: "grew 24%." still finds "grew 24%[1]."."""
    span = find_quote(sentence, text)
    if span or not MARKER.search(text):
        return span
    needle = collapse_whitespace(MARKER.sub("", sentence))
    kept: list[int] = []  # kept[i] is where the i-th kept character sits in `text`
    chars: list[str] = []
    cuts = [(m.start(), m.end()) for m in MARKER.finditer(text)]
    i = 0
    for start, end in [*cuts, (len(text), len(text))]:
        for j in range(i, start):
            ch = " " if text[j] == "\n" else text[j]
            if not (ch == " " and chars and chars[-1] == " "):
                chars.append(ch)
                kept.append(j)
        i = end
    found = "".join(chars).find(needle) if needle else -1
    if found < 0:
        return None
    return kept[found], kept[found + len(needle) - 1] + 1


def citations_for(parsed: ParsedAnswer, start: int, end: int) -> list[str]:
    """Citation ids inside `text[start:end]` or right after it, on the same line, in order."""
    found: list[str] = []
    pos = end
    for m in sorted(parsed.mentions, key=lambda m: m.start):
        if start <= m.start < end:
            found.append(m.citation_id)
        elif m.start >= end and set(parsed.text[pos : m.start]) <= GAP:
            found.append(m.citation_id)
            pos = max(pos, m.end)
        elif m.start >= end:
            break
    return list(dict.fromkeys(found))
