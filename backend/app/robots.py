from urllib.parse import urlparse, urljoin
import httpx
from urllib import robotparser

DEFAULT_AGENT = "EvidentiaBot"

async def is_allowed(url: str, agent: str = DEFAULT_AGENT) -> bool:
    """
    Async-friendly robots.txt check that fetches robots.txt with httpx
    and parses it using Python's stdlib robotparser (no native build needed).
    """
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    robots_url = urljoin(base, "/robots.txt")

    # Fetch robots.txt (don’t block the event loop with robotparser.read())
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            r = await client.get(robots_url)
            content = r.text if r.status_code == 200 else ""
    except Exception:
        # If robots.txt is unreachable, default to allow (common convention).
        return True

    rp = robotparser.RobotFileParser()
    # robotparser.parse() accepts an iterable of lines
    rp.parse(content.splitlines())
    return rp.can_fetch(agent, url)

