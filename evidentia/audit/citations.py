"""Find the citations in a pasted AI answer, with code (D-037, step 1).

Answers arrive in a few shapes: markdown links (`[IEA](https://...)`), bare addresses, and
numbered markers (`[1]`, `[^2]`, `[1, 3]`) with a numbered source list at the end. This turns
the answer into plain text the splitter can copy sentences from, and records where in that text
each citation sits. Which claim cites which page is decided from those positions, not by a model.

The source list may be one entry per line, or all on one line after "Sources:", as it arrives
when a paste loses its line breaks (D-043). A marker with no source it can be matched to is
recorded as unresolved, so its claim is never judged against some other page.
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
# "Sources:" in the middle of a line, followed by a numbered entry.
INLINE_HEADING = re.compile(
    r"(?:^|(?<=[\s.!?)\]]))(?:sources|citations|references)\s*:\s*(?=(?:\[\^?\d+\]|\d+[.)])\s*\S)",
    re.IGNORECASE,
)
SOURCES_WORD = re.compile(r"\b(?:sources|citations|references)\s*:", re.IGNORECASE)
BRACKET_ENTRY = re.compile(r"\[\^?(\d+)\]:?\s*")
DOTTED_ENTRY = re.compile(r"(?:^|(?<=\s))(\d+)[.)]\s+")
MARKDOWN_LINK = re.compile(rf"\[[^\]\n]*\]\({URL}\)")
BULLET = re.compile(r"^\s*[-*+•]\s*")
LINE_START = re.compile(r"^\s*(?:#{1,6}\s+|[-*+•]\s+)?")
MARKER = re.compile(r"\[\^?\d+(?:\s*,\s*\d+)*\]")
# What may sit between a sentence and a citation that still belongs to it: "...2023 [1][2]."
GAP = set(" \t.,;:!?()\"'")


class Cited(BaseModel):
    id: str  # "c1", "c2", ... one per distinct address
    url: str


class Mention(BaseModel):
    citation_id: str
    start: int  # where the citation sits in ParsedAnswer.text
    end: int


class Unresolved(BaseModel):
    """A numbered marker in the answer with no source it can be matched to."""

    marker: str
    start: int
    end: int


class ParsedAnswer(BaseModel):
    text: str  # the answer without its source list, links and markdown marks
    citations: list[Cited] = []
    mentions: list[Mention] = []
    unresolved: list[Unresolved] = []

    @property
    def unknown_markers(self) -> list[str]:
        return [u.marker for u in self.unresolved]


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
        self.unresolved: list[Unresolved] = []

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
                self.unresolved.append(Unresolved(marker=n, start=start, end=len(self.text)))
                continue
            cid = self.ids.setdefault(url, f"c{len(self.ids) + 1}")
            self.mentions.append(Mention(citation_id=cid, start=start, end=len(self.text)))

    def end_line(self, before: int) -> None:
        self.text = self.text.rstrip(" ")
        if len(self.text) == before:
            return
        self.text += "\n"
        for m in [*self.mentions, *self.unresolved]:  # one at a line's very end stays on it
            m.start, m.end = min(m.start, len(self.text) - 1), min(m.end, len(self.text) - 1)


MAX_REFERENCE_TITLE = 150  # longer than this, a numbered line is a list item, not a source


def is_reference(rest: str) -> bool:
    """A numbered line is a source if it is an address with at most a short title.

    "2. **A bright galaxy...** Webb confirmed it ([stsci.edu](https://...))" is a numbered list
    item that happens to cite a page: it has a markdown link and a long sentence, so it stays.
    A source written as a link, "[Title](https://...)", starts with the link.
    """
    link = MARKDOWN_LINK.match(rest)
    if link:
        return len(rest[link.end() :].strip()) <= MAX_REFERENCE_TITLE
    if "](" in rest:
        return False
    return len(FIRST_URL.sub("", rest).strip()) <= MAX_REFERENCE_TITLE


def split_entries(chunk: str) -> list[str] | None:
    """Several numbered sources on one line, as one "[n] rest" line each; None if it is not that."""
    for pattern in (BRACKET_ENTRY, DOTTED_ENTRY):
        marks = list(pattern.finditer(chunk))
        if len(marks) < 2 or chunk[: marks[0].start()].strip():
            continue
        entries = []
        for mark, following in zip(marks, [*marks[1:], None], strict=True):
            rest = chunk[mark.end() : following.start() if following else len(chunk)].strip()
            if not FIRST_URL.search(rest) or not is_reference(rest):
                break
            entries.append(f"[{mark[1]}] {rest}")
        else:
            return entries
    return None


def expand_lines(lines: list[str]) -> list[str]:
    """Put a source list that arrived on one line back on separate lines."""
    out: list[str] = []
    for line in lines:
        heading = INLINE_HEADING.search(line)
        if heading:
            before, chunk = line[: heading.start()].rstrip(), line[heading.end() :]
            out += ([before] if before else []) + ["Sources:"]
            out += split_entries(chunk) or [chunk]
        else:
            out += split_entries(line) or [line]
    return out


def is_unnumbered_source(line: str) -> bool:
    """Under a "Sources" heading: a line that is just an address and a short title."""
    rest = BULLET.sub("", line).strip()
    if not FIRST_URL.search(rest) or MARKER.search(rest):
        return False
    title = MARKDOWN_LINK.sub("", rest) if MARKDOWN_LINK.search(rest) else FIRST_URL.sub("", rest)
    return len(title.strip()) <= MAX_REFERENCE_TITLE


def references_in(lines: list[str]) -> tuple[dict[str, str], set[int]]:
    """Numbered source lines ("[1] Title https://...", "2. https://...") and where they are."""
    references, where = {}, set()
    under_heading = False
    for i, line in enumerate(lines):
        m = REFERENCE.match(line)
        if m and is_reference(m["rest"]):
            references.setdefault(m["a"] or m["b"], tidy_url(FIRST_URL.search(m["rest"]).group(0)))
            where.add(i)
        elif HEADING.match(line):
            where.add(i)
            under_heading = True
        elif under_heading and is_unnumbered_source(line):
            where.add(i)  # listed, but with no number a claim could point to
        elif line.strip():
            under_heading = False
    return references, where


def parse_answer(answer: str) -> ParsedAnswer:
    lines = expand_lines(answer.replace("\r\n", "\n").split("\n"))
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
        unresolved=builder.unresolved,
    )


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


def attached(parsed: ParsedAnswer, start: int, end: int) -> tuple[list[str], list[str]]:
    """What sits inside `text[start:end]` or right after it on the same line, in order:
    the citation ids, and the markers that could not be matched to a source."""
    cited: list[str] = []
    unread: list[str] = []
    pos = end
    for m in sorted([*parsed.mentions, *parsed.unresolved], key=lambda m: m.start):
        inside = start <= m.start < end
        right_after = m.start >= end and set(parsed.text[pos : m.start]) <= GAP
        if not inside and not right_after:
            if m.start >= end:
                break
            continue
        if right_after:
            pos = max(pos, m.end)
        if isinstance(m, Mention):
            cited.append(m.citation_id)
        else:
            unread.append(m.marker)
    return list(dict.fromkeys(cited)), list(dict.fromkeys(unread))


def citations_for(parsed: ParsedAnswer, start: int, end: int) -> list[str]:
    """Citation ids inside `text[start:end]` or right after it, on the same line, in order."""
    return attached(parsed, start, end)[0]


def paragraph_citations(parsed: ParsedAnswer, end: int) -> list[str]:
    """The citations of the next cited sentence in the same paragraph (line), if any.

    Many chat tools put one citation at the end of a paragraph for the whole of it. A sentence
    with no citation of its own is read as covered by the citation that closes its paragraph.
    """
    line_end = parsed.text.find("\n", end)
    line_end = len(parsed.text) if line_end < 0 else line_end
    after = sorted((m for m in parsed.mentions if end <= m.start < line_end), key=lambda m: m.start)
    if not after:
        return []
    first = after[0].start
    # Never borrow across a marker that could not be read, or from a source list left in the
    # text: that is how a claim came to be judged against another claim's page (D-043).
    between = parsed.text[end:first]
    if SOURCES_WORD.search(between) or any(end <= u.start < first for u in parsed.unresolved):
        return []
    return list(
        dict.fromkeys(
            m.citation_id
            for m in after
            if m.start == first or (set(parsed.text[first : m.start]) <= GAP | set("[]^0123456789"))
        )
    )
