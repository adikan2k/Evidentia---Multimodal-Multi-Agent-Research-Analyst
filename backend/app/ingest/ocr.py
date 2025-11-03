# backend/app/ingest/ocr.py
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import tempfile
import os
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

def extract_ocr_from_pdf(pdf_bytes: bytes, url: str) -> Optional[Dict[str, Any]]:
    try:
        images = convert_from_bytes(pdf_bytes, dpi=200, fmt="jpeg")
        ocr_text = []
        for img in images:
            text = pytesseract.image_to_string(img)
            ocr_text.append(text)
        full_text = "\n\n".join(ocr_text)
        if not full_text.strip():
            return None
        title = os.path.basename(urlparse(url).path) or "Scanned PDF"
        return {"text": full_text, "title": title, "url": url, "kind": "ocr"}
    except Exception:
        return None

def extract_figures_from_pdf(pdf_bytes: bytes, url: str) -> List[Dict[str, Any]]:
    figures = []
    try:
        images = convert_from_bytes(pdf_bytes, dpi=300, fmt="jpeg")
        for i, img in enumerate(images):
            # Simple heuristic: save image as figure; later we can filter by size/layout
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpeg") as tmp:
                img.save(tmp.name, "JPEG")
                figures.append({
                    "image_path": tmp.name,
                    "title": f"Figure {i+1}",
                    "url": url,
                    "kind": "figure"
                })
    except Exception:
        pass
    return figures
