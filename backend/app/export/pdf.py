# backend/app/export/pdf.py
from typing import Optional
import anyio

BASE_CSS = """
@page { size: A4; margin: 24mm; }
h1,h2,h3 { page-break-after: avoid; }
figure { page-break-inside: avoid; }
code, pre { white-space: pre-wrap; }
"""

def _weasyprint_sync(html_body: str, title: str) -> bytes:
    # Called inside a worker thread via anyio.to_thread.run_sync
    from weasyprint import HTML, CSS
    full = f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head><body>{html_body}</body></html>'
    return HTML(string=full, base_url=".").write_pdf(stylesheets=[CSS(string=BASE_CSS)])

async def _playwright_pdf_async(html_body: str, title: str) -> bytes:
    # Pure async Chromium renderer (no native deps)
    from playwright.async_api import async_playwright
    html = f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head><body>{html_body}</body></html>'
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        # Load HTML directly (no temp file needed)
        await page.set_content(html, wait_until="load")
        pdf_bytes = await page.pdf(
            format="A4",
            margin={"top": "24mm", "right": "24mm", "bottom": "24mm", "left": "24mm"},
            print_background=True,
        )
        await browser.close()
        return pdf_bytes

async def render_report_to_pdf_async(html_body: str, title: str = "Evidentia Report") -> bytes:
    # Try WeasyPrint first (in thread) — works in Docker/Linux where libs exist
    try:
        return await anyio.to_thread.run_sync(_weasyprint_sync, html_body, title)
    except Exception:
        # Fallback to Playwright (Windows-friendly)
        return await _playwright_pdf_async(html_body, title)


