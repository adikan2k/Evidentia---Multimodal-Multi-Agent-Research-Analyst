import asyncio
import socket

import httpcore
import httpx
import pytest

from evidentia.fetch import Fetcher
from evidentia.netguard import BlockedAddress, Unresolvable, guarded_transport, is_public_address
from evidentia.schemas import SearchHit
from evidentia.tracing import NoopTracer

PUBLIC_IP = "93.184.215.14"


def answers(*addresses: str):
    async def resolver(host: str, port: int) -> list[str]:
        return list(addresses)

    return resolver


class RecordingBackend(httpcore.AsyncMockBackend):
    """Answers every request with a small 200 response and remembers where it was sent."""

    def __init__(self) -> None:
        super().__init__([b"HTTP/1.1 200 OK\r\n", b"Content-Length: 2\r\n", b"\r\n", b"ok"])
        self.connected_to: list[str] = []

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        self.connected_to.append(host)
        return await super().connect_tcp(host, port, timeout, local_address, socket_options)


def get(url: str, resolver, inner=None) -> httpx.Response:
    async def go() -> httpx.Response:
        transport = guarded_transport(resolver=resolver, inner=inner)
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.get(url)

    return asyncio.run(go())


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.0.0.7", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),  # cloud metadata
        ("100.64.0.1", False),  # carrier-grade NAT
        ("::1", False),
        ("fe80::1%eth0", False),
        ("::ffff:127.0.0.1", False),  # loopback written as IPv6
        ("not an address", False),
    ],
)
def test_public_addresses(address: str, public: bool) -> None:
    assert is_public_address(address) is public


def test_a_public_name_that_resolves_to_loopback_is_refused_before_connecting() -> None:
    inner = RecordingBackend()
    with pytest.raises(BlockedAddress):
        get("http://friendly.example.org/", answers("127.0.0.1"), inner)
    assert inner.connected_to == []


def test_one_private_address_among_public_ones_is_enough_to_refuse() -> None:
    with pytest.raises(BlockedAddress):
        get("http://mixed.example.org/", answers(PUBLIC_IP, "10.0.0.7"), RecordingBackend())


def test_the_connection_goes_to_the_address_that_was_checked() -> None:
    # This is also the test that fails if an httpx upgrade stops the guard from being used.
    inner = RecordingBackend()
    response = get("http://friendly.example.org/", answers(PUBLIC_IP), inner)
    assert response.status_code == 200 and response.text == "ok"
    assert inner.connected_to == [PUBLIC_IP]


def test_a_name_that_does_not_resolve_is_a_network_error() -> None:
    async def fails(host: str, port: int) -> list[str]:
        raise OSError("no such host")

    with pytest.raises(httpx.ConnectError):
        get("http://missing.example.org/", fails, RecordingBackend())


def no_such_name(code: int):
    async def resolver(host: str, port: int) -> list[str]:
        raise socket.gaierror(code, "no such name")

    return resolver


def test_a_name_dns_says_does_not_exist_is_marked_as_such() -> None:
    with pytest.raises(httpx.ConnectError) as caught:
        get("http://gone.example.org/", no_such_name(socket.EAI_NONAME), RecordingBackend())
    assert isinstance(caught.value.__cause__, Unresolvable)


def test_a_temporary_dns_failure_is_not_called_a_missing_name() -> None:
    with pytest.raises(httpx.ConnectError) as caught:
        get("http://busy.example.org/", no_such_name(socket.EAI_AGAIN), RecordingBackend())
    assert not isinstance(caught.value.__cause__, Unresolvable)


def test_fetcher_reports_a_name_that_does_not_resolve(settings) -> None:
    transport = guarded_transport(resolver=no_such_name(socket.EAI_NONAME))
    fetcher = Fetcher(settings, NoopTracer(), client=httpx.AsyncClient(transport=transport))
    _, skipped = asyncio.run(fetcher.fetch_all([SearchHit(url="https://gone.example.org/x")]))
    assert skipped[0].reason == "name does not resolve"


def test_fetcher_skips_a_page_whose_name_points_inside(settings) -> None:
    client = httpx.AsyncClient(transport=guarded_transport(resolver=answers("169.254.169.254")))
    fetcher = Fetcher(settings, NoopTracer(), client=client)
    _, skipped = asyncio.run(fetcher.fetch_all([SearchHit(url="https://metadata.example.org/x")]))
    assert skipped[0].reason == "not a public address"


def test_fetcher_uses_the_guard_by_default(settings) -> None:
    fetcher = Fetcher(settings, NoopTracer())
    backend = fetcher.client._transport._pool._network_backend
    assert type(backend).__name__ == "GuardedBackend"
    asyncio.run(fetcher.aclose())
