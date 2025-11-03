from app.robots import is_allowed
from app.http_client import fetch_text

async def ingest_url(url: str) -> str:
    """
    Fetches the content of a URL, checking robots.txt first.
    Raises PermissionError if crawling is disallowed.
    """
    if not await is_allowed(url):
        raise PermissionError(f"Crawling disallowed by robots.txt: {url}")

    return await fetch_text(url, headers={"User-Agent": "EvidentiaBot/1.0"})
