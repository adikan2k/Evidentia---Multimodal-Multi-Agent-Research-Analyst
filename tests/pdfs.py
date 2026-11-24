"""Small PDFs built in code, so the tests need no files and no PDF-writing library."""

import io

from pypdf import PdfReader, PdfWriter


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content(lines: list[str]) -> bytes:
    if not lines:
        return b""
    shown = " ".join(f"({_escape(line)}) Tj T*" for line in lines)
    return f"BT /F1 11 Tf 14 TL 72 760 Td {shown} ET".encode("latin-1")


def make_pdf(pages: list[list[str]]) -> bytes:
    """A PDF with one page per item, each page a list of text lines in Helvetica."""
    count = len(pages)
    page_ids = [4 + 2 * i for i in range(count)]
    kids = " ".join(f"{n} 0 R" for n in page_ids)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for page_id, lines in zip(page_ids, pages, strict=True):
        stream = _content(lines)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode()
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(out)


def encrypt(pdf: bytes, password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf)))
    writer.encrypt(password, algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
