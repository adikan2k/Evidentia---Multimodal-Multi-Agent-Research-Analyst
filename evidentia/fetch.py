"""Download pages politely and turn them into the stored source text.

Everything fetched here is untrusted data. It is only ever stored, searched and quoted.
"""

import asyncio
import ipaddress
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from evidentia.config import Settings
from evidentia.schemas import SearchHit, SkippedPage, Source
from evidentia.tracing import Tracer

MAX_REDIRECTS = 5


class Skip(Exception):
    """A page we chose not to use. The reason is shown in the run report."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def clean_text(raw: str) -> str:
    """Single spaces inside a paragraph, one newline between paragraphs.

    `quote_check` relies on exactly this shape.
    """
    lines = (" ".join(line.split()) for line in raw.splitlines())
    return "\n".join(line for line in lines if line)


def extract_text(html: bytes) -> str:
    raw = trafilatura.extract(html, include_comments=False, favor_precision=True)
    return clean_text(raw or "")


def is_public_host(host: str) -> bool:
    """False for this machine, private networks and cloud-internal names.

    The API fetches pages a search engine suggests. This stops a page, or a redirect, from
    pointing the fetcher at something only the server can reach.
    """
    host = host.lower().rstrip(".")
    if not host or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True  # an ordinary name
    return address.is_global


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


class HostLimiter:
    """Makes callers wait so one host gets at most one request per `interval` seconds."""

    def __init__(
        self,
        interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last: dict[str, float] = {}

    async def wait(self, host: str) -> None:
        async with self._locks[host]:
            if host in self._last:
                delay = self._last[host] + self.interval - self.clock()
                if delay > 0:
                    await self.sleep(delay)
            self._last[host] = self.clock()


class Robots:
    """Reads each site's robots.txt once and answers whether we may fetch a URL."""

    def __init__(self, client: httpx.AsyncClient, limiter: HostLimiter, user_agent: str) -> None:
        self.client = client
        self.limiter = limiter
        self.user_agent = user_agent
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._rules: dict[str, RobotFileParser | None] = {}

    async def allowed(self, url: str) -> bool:
        origin = origin_of(url)
        async with self._locks[origin]:
            if origin not in self._rules:
                self._rules[origin] = await self._load(origin)
        rules = self._rules[origin]
        if rules is None:
            raise Skip("robots.txt could not be read")
        return rules.can_fetch(self.user_agent, url)

    async def _load(self, origin: str) -> RobotFileParser | None:
        await self.limiter.wait(origin)
        try:
            response = await self.client.get(f"{origin}/robots.txt", follow_redirects=True)
        except httpx.HTTPError:
            return None
        rules = RobotFileParser()
        if response.status_code in (401, 403):
            rules.disallow_all = True
        elif response.status_code >= 500:
            return None
        elif response.status_code >= 400:
            rules.allow_all = True  # no robots.txt means no restrictions
        else:
            rules.parse(response.text.splitlines())
        return rules


class Fetcher:
    def __init__(
        self,
        settings: Settings,
        tracer: Tracer,
        client: httpx.AsyncClient | None = None,
        limiter: HostLimiter | None = None,
    ) -> None:
        self.settings = settings
        self.tracer = tracer
        self.client = client or httpx.AsyncClient(timeout=settings.fetch_timeout_s)
        self.client.headers["User-Agent"] = settings.user_agent
        self.limiter = limiter or HostLimiter(settings.per_host_interval_s)
        self.robots = Robots(self.client, self.limiter, settings.user_agent)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def fetch_all(self, hits: list[SearchHit]) -> tuple[list[Source], list[SkippedPage]]:
        results = await asyncio.gather(*(self._one(hit.url) for hit in hits))
        sources, skipped = [], []
        for hit, result in zip(hits, results, strict=True):
            if isinstance(result, Skip):
                skipped.append(SkippedPage(url=hit.url, reason=result.reason))
            else:
                source_id = f"S{len(sources) + 1}"
                sources.append(Source(id=source_id, url=hit.url, title=hit.title, text=result))
        return sources, skipped

    async def _one(self, url: str) -> str | Skip:
        with self.tracer.span("fetch", "tool", {"url": url}) as span:
            try:
                html = await self.fetch_html(url)
                text = await asyncio.to_thread(extract_text, html)
                if len(text) < self.settings.min_page_chars:
                    raise Skip("no readable text")
            except Skip as skip:
                span.update(output={"skipped": skip.reason})
                return skip
            except httpx.HTTPError as err:
                span.update(output={"skipped": type(err).__name__})
                return Skip(f"network error ({type(err).__name__})")
            span.update(output={"chars": len(text)})
            return text

    async def fetch_html(self, url: str) -> bytes:
        """Follow redirects by hand so robots.txt and the rate limit apply to every hop."""
        for _ in range(MAX_REDIRECTS + 1):
            if urlsplit(url).scheme not in ("http", "https"):
                raise Skip("not an http(s) address")
            if not is_public_host(urlsplit(url).hostname or ""):
                raise Skip("not a public address")
            if not await self.robots.allowed(url):
                raise Skip("disallowed by robots.txt")
            await self.limiter.wait(origin_of(url))
            async with self.client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.status_code != 200:
                    raise Skip(f"HTTP {response.status_code}")
                if "html" not in response.headers.get("content-type", ""):
                    raise Skip("not an HTML page")
                return await self._read_capped(response)
        raise Skip("too many redirects")

    async def _read_capped(self, response: httpx.Response) -> bytes:
        body = b""
        async for part in response.aiter_bytes():
            body += part
            if len(body) > self.settings.fetch_max_bytes:
                raise Skip("page is larger than the size limit")
        return body
