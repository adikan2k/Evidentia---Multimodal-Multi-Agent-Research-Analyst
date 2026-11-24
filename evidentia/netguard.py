"""Connect only to public addresses, checked at the moment of connecting (D-035).

The fetcher follows links from search results and, later, from visitors. A public-looking name
can resolve to this server's own network, or to the cloud metadata address. So every
connection resolves the name, refuses if any address is not public, and then connects to the
very address it checked. That last step also defeats a name that answers differently the
second time it is asked (DNS rebinding).
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Iterable

import httpcore
import httpx

Resolver = Callable[[str, int], Awaitable[list[str]]]

RESOLVE_TIMEOUT_S = 10.0


class BlockedAddress(Exception):
    """A host name that resolves to an address only this server can reach."""


class Unresolvable(httpcore.ConnectError):
    """DNS says the name does not exist. The auditor reports this as a dead link."""


# getaddrinfo's "no such name" codes. Other failures, such as a DNS server timing out, may pass,
# so they stay ordinary connection errors.
NO_SUCH_NAME = {code for code in (socket.EAI_NONAME, getattr(socket, "EAI_NODATA", None)) if code}


async def resolve(host: str, port: int) -> list[str]:
    """Every address the name resolves to, in the order the system gives them."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%")[0])  # drop an IPv6 zone such as "%eth0"
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped  # "::ffff:127.0.0.1" is loopback in disguise
    return ip.is_global


class GuardedBackend(httpcore.AsyncNetworkBackend):
    """httpcore's network layer, with the address check in front of every TCP connection."""

    def __init__(
        self, inner: httpcore.AsyncNetworkBackend | None = None, resolver: Resolver = resolve
    ) -> None:
        self.inner = inner or httpcore.AnyIOBackend()
        self.resolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await asyncio.wait_for(
                self.resolver(host, port), timeout or RESOLVE_TIMEOUT_S
            )
        except socket.gaierror as err:
            if err.errno in NO_SUCH_NAME:
                raise Unresolvable(f"{host} does not resolve") from err
            raise httpcore.ConnectError(f"could not resolve {host}") from err
        except (OSError, TimeoutError) as err:
            raise httpcore.ConnectError(f"could not resolve {host}") from err
        if not addresses or not all(is_public_address(a) for a in addresses):
            raise BlockedAddress(host)
        # TLS is set up by httpcore afterwards and still checks the certificate against `host`.
        return await self.inner.connect_tcp(
            addresses[0],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise BlockedAddress(path)

    async def sleep(self, seconds: float) -> None:
        await self.inner.sleep(seconds)


def guarded_transport(
    resolver: Resolver = resolve, inner: httpcore.AsyncNetworkBackend | None = None
) -> httpx.AsyncHTTPTransport:
    """An httpx transport that can only reach public addresses. No proxy settings are read."""
    transport = httpx.AsyncHTTPTransport(trust_env=False)
    # httpx 0.28.1 has no public way to choose the network backend, so the transport gets a pool
    # that uses ours. tests/test_netguard.py fails if an upgrade stops this from taking effect.
    transport._pool = httpcore.AsyncConnectionPool(
        ssl_context=httpx.create_ssl_context(trust_env=False),
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=5.0,
        network_backend=GuardedBackend(inner, resolver),
    )
    return transport
