# backend/app/ingest/pdf.py
import pdfplumber
import camelot
from typing import Optional, Dict, Any, List
import tempfile
import os
from urllib.parse import urlparse

def extract_pdf_text(pdf_bytes: bytes, url: str) -> Optional[Dict[str, Any]]:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        with pdfplumber.open(tmp_path) as pdf:
            full_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
        os.unlink(tmp_path)
        if not full_text.strip():
            return None
        title = os.path.basename(urlparse(url).path) or "PDF Document"
        return {"text": full_text, "title": title, "url": url, "kind": "pdf"}
    except Exception:
        return None

def extract_pdf_tables(pdf_bytes: bytes, url: str) -> List[Dict[str, Any]]:
    tables = []
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        tables_camelot = camelot.read_pdf(tmp_path, pages="all", flavor="lattice")
        for i, table in enumerate(tables_camelot):
            tables.append({
                "table": table.df.to_markdown(index=False),
                "title": f"Table {i+1}",
                "url": url,
                "kind": "table"
            })
        os.unlink(tmp_path)
    except Exception:
        pass
    return tables
