"""Download pages politely and turn them into the stored source text.

Everything fetched here is untrusted data. It is only ever stored, searched and quoted.
"""

import asyncio
import ipaddress
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura

from evidentia.config import Settings
from evidentia.netguard import BlockedAddress, guarded_transport
from evidentia.pdf import Unreadable, read_pdf
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


Kind = Literal["html", "pdf"]


@dataclass
class Body:
    data: bytes
    kind: Kind


def expected_kind(content_type: str) -> Kind | None:
    """What a response says it is. PDFs are often served as plain binary, so that counts too."""
    content_type = content_type.lower()
    if "html" in content_type:
        return "html"
    if "application/pdf" in content_type or "octet-stream" in content_type:
        return "pdf"
    return None


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
        self.client = client or httpx.AsyncClient(
            timeout=settings.fetch_timeout_s, transport=guarded_transport(), trust_env=False
        )
        self.client.headers["User-Agent"] = settings.user_agent
        self.limiter = limiter or HostLimiter(settings.per_host_interval_s)
        self.robots = Robots(self.client, self.limiter, settings.user_agent)

    async def aclose(self) -> None:
        await self.client.aclose()

    async def fetch_all(self, hits: list[SearchHit]) -> tuple[list[Source], list[SkippedPage]]:
        results = await asyncio.gather(*(self._one(hit) for hit in hits))
        sources, skipped = [], []
        for hit, result in zip(hits, results, strict=True):
            if isinstance(result, Skip):
                skipped.append(SkippedPage(url=hit.url, reason=result.reason))
            else:
                sources.append(result.model_copy(update={"id": f"S{len(sources) + 1}"}))
        return sources, skipped

    async def _one(self, hit: SearchHit) -> Source | Skip:
        with self.tracer.span("fetch", "tool", {"url": hit.url}) as span:
            try:
                body = await self.fetch_body(hit.url)
                if body.kind == "pdf":
                    source = await self.read_pdf(hit, body.data)
                else:
                    text = await asyncio.to_thread(extract_text, body.data)
                    if len(text) < self.settings.min_page_chars:
                        raise Skip("no readable text")
                    source = Source(id="", url=hit.url, title=hit.title, text=text)
            except Skip as skip:
                span.update(output={"skipped": skip.reason})
                return skip
            except BlockedAddress:
                span.update(output={"skipped": "resolves to a non-public address"})
                return Skip("not a public address")
            except httpx.HTTPError as err:
                span.update(output={"skipped": type(err).__name__})
                return Skip(f"network error ({type(err).__name__})")
            span.update(output={"kind": source.kind, "chars": len(source.text)})
            return source

    async def read_pdf(self, hit: SearchHit, data: bytes) -> Source:
        s = self.settings
        try:
            pdf = await asyncio.wait_for(
                asyncio.to_thread(read_pdf, data, s.pdf_max_pages), s.pdf_timeout_s
            )
        except TimeoutError as err:
            raise Skip("PDF took too long to read") from err
        except Unreadable as err:
            raise Skip(err.reason) from err
        if len(pdf.text) < s.min_page_chars:
            raise Skip("scanned PDF, no text")
        return Source(
            id="",
            url=hit.url,
            title=hit.title,
            text=pdf.text,
            kind="pdf",
            page_starts=pdf.page_starts,
            pages_total=pdf.pages_total,
        )

    async def fetch_body(self, url: str) -> Body:
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
                return await self._read_body(response)
        raise Skip("too many redirects")

    async def _read_body(self, response: httpx.Response) -> Body:
        kind = expected_kind(response.headers.get("content-type", ""))
        if kind is None:
            raise Skip("not an HTML page or PDF")
        if kind == "pdf":
            data = await self._read_capped(response, self.settings.pdf_max_bytes, "PDF")
        else:
            data = await self._read_capped(response, self.settings.fetch_max_bytes, "page")
        if data.startswith(b"%PDF-"):
            return Body(data, "pdf")
        if kind == "pdf":
            raise Skip("not a valid PDF")
        return Body(data, "html")

    async def _read_capped(self, response: httpx.Response, limit: int, what: str) -> bytes:
        too_big = Skip(f"{what} is larger than the size limit")
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            raise too_big
        body = bytearray()
        async for part in response.aiter_bytes():
            body += part
            if len(body) > limit:
                raise too_big
        return bytes(body)
