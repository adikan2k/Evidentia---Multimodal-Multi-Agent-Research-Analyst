import httpx, asyncio, random, time
from contextlib import asynccontextmanager
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0, read=8.0)
DEFAULT_HEADERS = {
    "User-Agent": "EvidentiaBot/0.1 (+https://example.org/bot) contact: research@example.org",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

@asynccontextmanager
async def client():
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        http2=True,
    ) as c:
        yield c

async def get_with_retry(url: str, max_tries: int = 3, backoff: float = 0.6) -> httpx.Response:
    last: Optional[Exception] = None
    for attempt in range(1, max_tries + 1):
        try:
            async with client() as c:
                return await c.get(url)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last = e
            sleep = backoff * (2 ** (attempt - 1)) * (1 + random.random() * 0.2)
            await asyncio.sleep(sleep)
    assert last is not None
    raise last
@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=8),
    retry=retry_if_exception_type((
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.RemoteProtocolError,
        httpx.HTTPStatusError,
    )),
)
async def fetch_text(url: str, headers: dict | None = None) -> str:
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.text