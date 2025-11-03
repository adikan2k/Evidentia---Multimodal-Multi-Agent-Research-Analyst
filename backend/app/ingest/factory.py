# backend/app/ingest/factory.py
from urllib.parse import urlparse
import httpx
from .html import extract_html
from .pdf import extract_pdf_text, extract_pdf_tables
from .youtube import extract_youtube_transcript
from .ocr import extract_ocr_from_pdf, extract_figures_from_pdf
from .multimodal import caption_image
from typing import List, Dict, Any, Optional

async def ingest_url(url: str) -> List[Dict[str, Any]]:
    parsed = urlparse(url)
    results = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "").lower()
        if "html" in content_type or parsed.scheme in ("http", "https") and not any(ext in parsed.path.lower() for ext in (".pdf", ".mp4")):
            data = extract_html(resp.text, url)
            if data:
                results.append(data)
        elif "pdf" in content_type or parsed.path.lower().endswith(".pdf"):
            pdf_bytes = resp.content
            # Try text extraction first
            data = extract_pdf_text(pdf_bytes, url)
            if data:
                results.append(data)
            # Fallback OCR if text extraction fails or is minimal
            if not data or len(data["text"]) < 200:
                ocr = extract_ocr_from_pdf(pdf_bytes, url)
                if ocr:
                    results.append(ocr)
            # Extract tables
            tables = extract_pdf_tables(pdf_bytes, url)
            results.extend(tables)
            # Extract figures for multimodal captioning (optional)
            figures = extract_figures_from_pdf(pdf_bytes, url)
            for fig in figures:
                caption = caption_image(fig["image_path"], url)
                if caption:
                    results.append(caption)
        elif "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
            data = extract_youtube_transcript(url)
            if data:
                results.append(data)
        else:
            # Unsupported for now
            pass
    return results
