"""Turn a PDF's text layer into stored source text that knows where each page starts (D-030).

A PDF is untrusted data, like a web page: its text is only ever stored, searched and quoted.
"""

import io
import logging
import re
from dataclasses import dataclass

from pypdf import PasswordType, PdfReader

# pypdf logs a warning for every font quirk it works around, which buries the run's own output.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# A word split over a line end, as in "evi-" + "dence": joined without the hyphen. When the next
# line starts with a capital or a digit, as in "COVID-" + "19", the hyphen is part of the word
# and is kept, with no space after it.
_HYPHEN_BREAK = re.compile(r"(\w)-[ \t]*\n\s*([a-z])")
_HYPHEN_KEPT = re.compile(r"(\w)-[ \t]*\n\s*(?=[A-Z0-9])")


class Unreadable(Exception):
    """A PDF we cannot use. The reason is shown in the run report."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class PdfText:
    text: str
    page_starts: list[int]  # offset in `text` where each page read begins; one per page
    pages_total: int  # pages in the document, including any past the page limit


def clean_page(raw: str) -> str:
    """One page as one line: hyphen breaks joined, all whitespace collapsed to single spaces.

    `quote_check` relies on stored text having single spaces and no blank lines.
    """
    joined = _HYPHEN_KEPT.sub(r"\1-", _HYPHEN_BREAK.sub(r"\1\2", raw))
    return " ".join(joined.split())


def join_pages(pages: list[str]) -> tuple[str, list[int]]:
    """Pages joined by newlines, and where each starts. An empty page starts where the next does."""
    starts, kept, pos = [], [], 0
    for page in pages:
        starts.append(pos)
        if page:
            kept.append(page)
            pos += len(page) + 1
    return "\n".join(kept), starts


def _open(data: bytes) -> PdfReader:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        # Many PDFs are encrypted only to set permissions, with an empty password to open them.
        try:
            opened = reader.decrypt("")
        except Exception as err:  # e.g. AES without the optional crypto package
            raise Unreadable("encrypted PDF") from err
        if opened == PasswordType.NOT_DECRYPTED:
            raise Unreadable("encrypted PDF")
    return reader


def read_pdf(data: bytes, max_pages: int) -> PdfText:
    """The text of the first `max_pages` pages. Raises `Unreadable` for anything we cannot use."""
    try:
        reader = _open(data)
        total = len(reader.pages)
        pages = [clean_page(reader.pages[i].extract_text()) for i in range(min(total, max_pages))]
    except Unreadable:
        raise
    except Exception as err:  # pypdf raises many kinds of error on a malformed file
        raise Unreadable("could not read the PDF") from err
    text, starts = join_pages(pages)
    return PdfText(text=text, page_starts=starts, pages_total=total)
