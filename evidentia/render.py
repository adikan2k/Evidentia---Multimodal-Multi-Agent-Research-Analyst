"""A second reader, for pages that show their text only after scripts run (D-046).

A headless browser loads the page and runs its scripts. The browser never touches the network
itself: every request the page makes is handed to `Gate`, which makes it with the fetcher's own
client. So the same name, the same robots.txt check and the same guard against private addresses
apply to each request and to each redirect of it. The browser is also given a proxy that leads
nowhere, so a request that slipped past the gate would fail instead of going out.

It only reads. GET requests only, nothing is clicked, and each page gets a fresh profile.
"""

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from evidentia.config import Settings
from evidentia.fetch import (
    MAX_REDIRECTS,
    NO_READABLE_TEXT,
    Fetcher,
    HostLimiter,
    Skip,
    extract_text,
    is_public_host,
    origin_of,
)
from evidentia.netguard import BlockedAddress
from evidentia.schemas import Source
from evidentia.tracing import Tracer

# What a page may load: itself, its scripts, and the data its scripts ask for. Images, video,
# fonts and stylesheets add load on the site and no text.
ALLOWED_KINDS = {"document", "script", "xhr", "fetch"}
# Sent on from the page's own request. The user agent is always ours.
FORWARDED = ("accept", "origin", "referer")
# Headers that describe the bytes on the wire, which httpx has already decoded, and cookies,
# which are not kept.
DROPPED = {"content-encoding", "content-length", "transfer-encoding", "connection", "set-cookie"}
NOWHERE = {"server": "http://127.0.0.1:9", "bypass": "<-loopback>"}  # the proxy that leads nowhere
QUIET_S = 0.5  # the page is taken as settled after this long with no request in flight
BROWSER_FAILED = "the browser could not load the page"


class Refused(Exception):
    """A request the gate will not make, or could not."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Reply:
    url: str  # where the answer came from, after any redirects
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass
class Gate:
    """Every request of one page load passes through here."""

    fetcher: Fetcher
    settings: Settings
    limiter: HostLimiter  # the short wait between requests inside one page load
    made: int = 0
    refused: Counter = field(default_factory=Counter)
    in_flight: int = 0
    last_change: float = field(default_factory=time.monotonic)

    def refusal(self, method: str, kind: str, url: str, main_frame: bool = True) -> str | None:
        """Why this request is not made, or None if it may be."""
        if method != "GET":
            return "not a GET request"
        if kind not in ALLOWED_KINDS:
            return f"{kind} is not loaded"
        if kind == "document" and not main_frame:
            return "a page inside the page is not loaded"
        if urlsplit(url).scheme not in ("http", "https"):
            return "not an http(s) address"
        if self.made >= self.settings.render_max_requests:
            return "over the request limit for one page"
        return None

    async def answer(
        self, method: str, kind: str, url: str, headers: dict[str, str], main_frame: bool = True
    ) -> Reply:
        """Make the request the page asked for, or raise `Refused`. Counts both."""
        why = self.refusal(method, kind, url, main_frame)
        if why is None:
            self.made += 1
            self.in_flight += 1
            try:
                return await self.get(url, headers, document=kind == "document")
            except Refused as refused:
                why = refused.reason
            finally:
                self.in_flight -= 1
                self.last_change = time.monotonic()
        self.refused[why] += 1
        raise Refused(why)

    async def get(self, url: str, headers: dict[str, str], document: bool = False) -> Reply:
        """One GET, with redirects followed by hand so every hop is checked like a fetch."""
        sent = {k: v for k, v in headers.items() if k.lower() in FORWARDED}
        limiter = self.fetcher.limiter if document else self.limiter
        try:
            for _ in range(MAX_REDIRECTS + 1):
                if urlsplit(url).scheme not in ("http", "https"):
                    raise Refused("not an http(s) address")
                if not is_public_host(urlsplit(url).hostname or ""):
                    raise Refused("not a public address")
                if not await self.fetcher.robots.allowed(url):
                    raise Refused("disallowed by robots.txt")
                await limiter.wait(origin_of(url))
                async with self.fetcher.client.stream("GET", url, headers=sent) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers["location"])
                        continue
                    body = await self.fetcher._read_capped(
                        response, self.settings.fetch_max_bytes, "page"
                    )
                    kept = {k: v for k, v in response.headers.items() if k.lower() not in DROPPED}
                    return Reply(url, response.status_code, kept, body)
        except Skip as skip:
            raise Refused(skip.reason) from skip
        except BlockedAddress as err:
            raise Refused("not a public address") from err
        except httpx.HTTPError as err:
            raise Refused(f"network error ({type(err).__name__})") from err
        raise Refused("too many redirects")

    def settled(self) -> bool:
        return self.in_flight == 0 and time.monotonic() - self.last_change >= QUIET_S


class Renderer:
    def __init__(self, settings: Settings, fetcher: Fetcher, tracer: Tracer) -> None:
        self.settings = settings
        self.fetcher = fetcher
        self.tracer = tracer
        self.limiter = HostLimiter(settings.render_request_interval_s)
        self.one_at_a_time = asyncio.Lock()
        self._playwright: Any = None
        self._browser: Any = None

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            await self._playwright.stop()
            self._browser = self._playwright = None

    async def browser(self) -> Any:
        if self._browser is None:
            # Imported here: the server does not install Playwright (pyproject, group "render").
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True, proxy=NOWHERE)
        return self._browser

    async def render(self, url: str, title: str = "") -> Source | Skip:
        """The page's text after its scripts have run, or why it could not be read."""
        gate = Gate(self.fetcher, self.settings, self.limiter)
        with self.tracer.span("render", "tool", {"url": url}) as span:
            try:
                first = await gate.answer("GET", "document", url, {})
                if first.status != 200:
                    raise Skip(f"HTTP {first.status}")
                if "html" not in first.headers.get("content-type", "").lower():
                    raise Skip("not an HTML page")
                async with self.one_at_a_time:
                    html = await self.load(first, gate)
                text = await asyncio.to_thread(extract_text, html.encode())
                if len(text) < self.settings.min_page_chars:
                    raise Skip(NO_READABLE_TEXT)
            except Refused as refused:
                span.update(output={"skipped": refused.reason})
                return Skip(refused.reason)
            except Skip as skip:
                span.update(output={"skipped": skip.reason, "requests": gate.made})
                return skip
            span.update(
                output={"chars": len(text), "requests": gate.made, "refused": dict(gate.refused)}
            )
            return Source(id="", url=url, title=title, text=text, read_by="render")

    async def load(self, first: Reply, gate: Gate) -> str:
        """Open the fetched document in a fresh browser profile and return the HTML it becomes."""
        from playwright.async_api import Error as BrowserError

        browser = await self.browser()
        context = await browser.new_context(
            user_agent=self.settings.user_agent, accept_downloads=False, service_workers="block"
        )
        deadline = time.monotonic() + self.settings.render_timeout_s
        handed_over = False

        async def handle(route: Any) -> None:
            nonlocal handed_over
            request = route.request
            try:
                main = request.frame.parent_frame is None
                if not handed_over and request.url == first.url and main:
                    handed_over = True  # the document itself was fetched before the browser began
                    reply = first
                else:
                    reply = await gate.answer(
                        request.method, request.resource_type, request.url, request.headers, main
                    )
            except Refused:
                reply = None
            try:
                if reply is None:
                    await route.abort("blockedbyclient")
                else:
                    await route.fulfill(status=reply.status, headers=reply.headers, body=reply.body)
            except BrowserError:
                pass  # the page was closed while this request was still being answered

        try:
            await context.route("**/*", handle)
            page = await context.new_page()
            page.on("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))
            await page.goto(
                first.url,
                wait_until="domcontentloaded",
                timeout=self.settings.render_timeout_s * 1000,
            )
            gate.last_change = time.monotonic()  # give the scripts a moment to start asking
            while not gate.settled() and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            return await page.content()
        except BrowserError as err:
            raise Skip(BROWSER_FAILED) from err
        finally:
            await context.close()
