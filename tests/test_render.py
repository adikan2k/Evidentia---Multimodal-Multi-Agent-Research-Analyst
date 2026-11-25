"""The second page reader (D-046). The network is always a fake; one test uses a real browser."""

import asyncio

import httpx
import pytest

from evidentia.audit.graph import AuditDeps, AuditNodes
from evidentia.fetch import NO_READABLE_TEXT, Fetcher, HostLimiter, Skip
from evidentia.render import Gate, Refused, Renderer
from evidentia.schemas import SkippedPage, Source
from evidentia.tracing import NoopTracer

SITE = "https://site.example"
WRITTEN = (
    "Solar capacity grew 24% in 2023, the fastest rate on record, according to the agency. "
    "Analysts expect the pace to continue as panel prices keep falling across every market. "
    "Wind additions were slower over the same period, held back by permitting delays."
)
SHELL = (
    "<html><body><main id='app'></main><script src='/app.js'></script>"
    "<img src='/p.png'></body></html>"
)
SCRIPT = """
const app = document.getElementById('app');
fetch('/data.json?ua=' + encodeURIComponent(navigator.userAgent))
  .then(r => r.json())
  .then(d => { app.innerHTML = '<article><p>' + d.text + '</p></article>'; });
fetch('/log', {method: 'POST', body: 'x'}).catch(() => {});
"""


def make_gate(settings, handler, **changes) -> Gate:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = settings.model_copy(update=changes)
    return Gate(Fetcher(settings, NoopTracer(), client=client), settings, HostLimiter(0.0))


def plain(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    return httpx.Response(
        200, headers={"content-type": "text/html", "set-cookie": "a=1"}, text="ok"
    )


def refused(gate: Gate, *args, **kwargs) -> str:
    with pytest.raises(Refused) as caught:
        asyncio.run(gate.answer(*args, **kwargs))
    return caught.value.reason


def test_only_reading_requests_for_text_are_made(settings) -> None:
    gate = make_gate(settings, plain)
    assert refused(gate, "POST", "fetch", f"{SITE}/api", {}) == "not a GET request"
    assert refused(gate, "GET", "image", f"{SITE}/p.png", {}) == "image is not loaded"
    assert refused(gate, "GET", "stylesheet", f"{SITE}/s.css", {}) == "stylesheet is not loaded"
    assert "inside the page" in refused(gate, "GET", "document", f"{SITE}/ad", {}, main_frame=False)
    assert refused(gate, "GET", "script", "ftp://site.example/x", {}) == "not an http(s) address"
    assert gate.made == 0 and sum(gate.refused.values()) == 5


def test_requests_carry_our_name_and_only_the_headers_we_pass_on(settings) -> None:
    sent: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers)
        return plain(request)

    gate = make_gate(settings, handler)
    asked = {"user-agent": "Mozilla/5.0 Chrome", "origin": SITE, "cookie": "id=7", "accept": "*/*"}
    reply = asyncio.run(gate.answer("GET", "fetch", f"{SITE}/data.json", asked))
    assert all(h["user-agent"] == settings.user_agent for h in sent)
    page = sent[-1]
    assert page["origin"] == SITE and "cookie" not in page
    assert reply.status == 200 and "set-cookie" not in reply.headers and gate.made == 1


def test_robots_and_private_addresses_are_checked_on_every_hop(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        if path == "/robots.txt":
            closed = host == "closed.example"
            return (
                httpx.Response(200, text="User-agent: *\nDisallow: /")
                if closed
                else httpx.Response(404)
            )
        if path == "/to-closed":
            return httpx.Response(302, headers={"location": "https://closed.example/x"})
        if path == "/to-inside":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})
        return plain(request)

    gate = make_gate(settings, handler)
    assert (
        refused(gate, "GET", "script", "https://closed.example/a.js", {})
        == "disallowed by robots.txt"
    )
    assert refused(gate, "GET", "fetch", f"{SITE}/to-closed", {}) == "disallowed by robots.txt"
    assert refused(gate, "GET", "fetch", f"{SITE}/to-inside", {}) == "not a public address"
    assert refused(gate, "GET", "fetch", "http://localhost:8000/x", {}) == "not a public address"
    assert refused(gate, "GET", "fetch", "http://10.0.0.5/x", {}) == "not a public address"


def test_a_page_may_make_only_so_many_requests(settings) -> None:
    gate = make_gate(settings, plain, render_max_requests=2)
    for _ in range(2):
        asyncio.run(gate.answer("GET", "script", f"{SITE}/a.js", {}))
    assert (
        refused(gate, "GET", "script", f"{SITE}/b.js", {}) == "over the request limit for one page"
    )
    assert gate.made == 2


def test_a_real_browser_reads_text_that_a_script_writes(settings) -> None:
    pytest.importorskip("playwright")
    from playwright.async_api import Error as BrowserError

    seen: list[tuple[str, str, str]] = []
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers["user-agent"]))
        if request.url.path == "/data.json":
            asked.append(str(request.url))
        path = request.url.path
        if path == "/page":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=SHELL)
        if path == "/app.js":
            return httpx.Response(
                200, headers={"content-type": "application/javascript"}, text=SCRIPT
            )
        if path == "/data.json":
            return httpx.Response(200, json={"text": WRITTEN})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    fetcher = Fetcher(settings, NoopTracer(), client=client)
    renderer = Renderer(settings, fetcher, NoopTracer())

    async def run():
        try:
            return await renderer.render(f"{SITE}/page", "T")
        finally:
            await renderer.aclose()

    try:
        source = asyncio.run(run())
    except BrowserError as err:
        pytest.skip(f"the headless browser is not installed: {str(err)[:60]}")
    assert isinstance(source, Source) and source.read_by == "render"
    assert WRITTEN in source.text
    paths = [path for _, path, _ in seen]
    assert "/data.json" in paths and "/p.png" not in paths and "/log" not in paths
    assert all(method == "GET" and agent == settings.user_agent for method, _, agent in seen)
    # The page's own scripts see our name too, not a browser's.
    assert "EvidentiaBot" in asked[0] and "Mozilla" not in asked[0]


class FakeRenderer:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    async def render(self, url: str, title: str = "") -> Source | Skip:
        self.asked.append(url)
        if url not in self.pages:
            return Skip("no readable text")
        return Source(id="", url=url, title=title, text=self.pages[url], read_by="render")


def test_thin_pages_get_a_second_read_and_refusals_do_not(settings) -> None:
    settings = settings.model_copy(update={"audit_min_page_chars": 2000})
    long_text = "word " * 600
    renderer = FakeRenderer(
        {"https://thin.example/a": long_text, "https://empty.example/b": long_text}
    )
    deps = AuditDeps(
        settings=settings,
        ledger=None,
        tracer=NoopTracer(),
        llm=None,
        fetcher=None,
        embedder=None,
        renderer=renderer,
    )  # type: ignore[arg-type]
    sources = [
        Source(id="S1", url="https://thin.example/a", text="short"),
        Source(id="S2", url="https://still.example/c", text="short too"),
        Source(id="S3", url="https://fine.example/d", text=long_text),
    ]
    skipped = [
        SkippedPage(url="https://empty.example/b", reason=NO_READABLE_TEXT),
        SkippedPage(url="https://no.example/e", reason="HTTP 403"),
        SkippedPage(url="https://robots.example/f", reason="disallowed by robots.txt"),
    ]
    read, still = asyncio.run(AuditNodes(deps).second_read(sources, skipped))
    assert renderer.asked == [
        "https://thin.example/a",
        "https://still.example/c",
        "https://empty.example/b",
    ]
    by_url = {s.url: s for s in read}
    assert (
        by_url["https://thin.example/a"].read_by == "render"
        and by_url["https://thin.example/a"].id == "S1"
    )
    assert by_url["https://still.example/c"].text == "short too"  # nothing better came back
    assert by_url["https://fine.example/d"].read_by == "fetch"
    assert by_url["https://empty.example/b"].id == "S4"
    assert [p.reason for p in still] == ["HTTP 403", "disallowed by robots.txt"]
