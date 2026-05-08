"""SSRF guard (PR m5-pr15).

`safe_fetch` wraps httpx with an allowlist-style URL guard. Any request
to a private, link-local, loopback, or cloud-metadata address is
refused before the socket opens.

Toggleable via ``SAFE_FETCH_ENFORCE`` (default ``true``). Setting it to
``false`` is the rollback path — the wrapper still resolves and logs
but no longer raises, so a bad migration can be neutralised in seconds.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

import httpx


class UnsafeURLError(ValueError):
    """Raised when a URL targets a blocked address or scheme."""


# Cloud-provider metadata IPs / hosts. These never serve user-routable
# content; any code path reaching them through a URL parameter is
# almost certainly an SSRF.
_METADATA_HOSTS: frozenset[str] = frozenset({
    "169.254.169.254",       # AWS, GCP, Azure IMDS
    "metadata.google.internal",
    "metadata",
    "100.100.100.200",       # Alibaba ECS
    "fd00:ec2::254",         # AWS IMDSv6
})

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


@dataclass(frozen=True)
class GuardConfig:
    """Per-call relaxation knobs. Defaults are the strict policy."""

    allow_private: bool = False           # let RFC1918 / ULA through
    allow_loopback: bool = False
    allow_metadata: bool = False
    extra_blocked_hosts: Sequence[str] = ()


def is_enforced() -> bool:
    return os.getenv("SAFE_FETCH_ENFORCE", "true").lower() not in ("0", "false", "no", "off")


def _resolve(host: str) -> list[ipaddress._BaseAddress]:
    """Resolve host to all A/AAAA records (deduped)."""
    seen: set[str] = set()
    out: list[ipaddress._BaseAddress] = []
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"dns_failure: {host}: {exc}") from exc
    for fam, *_rest, sockaddr in infos:
        ip_str = sockaddr[0]
        if ip_str in seen:
            continue
        seen.add(ip_str)
        try:
            out.append(ipaddress.ip_address(ip_str))
        except ValueError:
            continue
    return out


def _ip_blocked(ip: ipaddress._BaseAddress, cfg: GuardConfig) -> Optional[str]:
    if ip.is_loopback:
        return None if cfg.allow_loopback else "loopback"
    if ip.is_link_local:
        return "link_local"
    if ip.is_multicast:
        return "multicast"
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_reserved:
        return "reserved"
    if ip.is_private and not cfg.allow_private:
        return "private"
    return None


def assert_safe_url(url: str, *, config: Optional[GuardConfig] = None) -> None:
    """Raise :class:`UnsafeURLError` if ``url`` targets a blocked address.

    Pure validator — no socket is opened beyond DNS resolution. Safe to
    call at request-validation time before handing the URL to httpx.
    """
    cfg = config or GuardConfig()
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"bad_scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UnsafeURLError("missing_host")
    if not cfg.allow_metadata and host in _METADATA_HOSTS:
        raise UnsafeURLError(f"metadata_host: {host}")
    if host in {h.lower() for h in cfg.extra_blocked_hosts}:
        raise UnsafeURLError(f"blocked_host: {host}")

    # Literal IP in the URL: validate directly.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        reason = _ip_blocked(literal, cfg)
        if reason:
            raise UnsafeURLError(f"blocked_ip: {literal} ({reason})")
        return

    # Hostname: resolve and verify every record. Mixed result sets (one
    # public + one private) still fail closed.
    addrs = _resolve(host)
    if not addrs:
        raise UnsafeURLError(f"no_address_records: {host}")
    for ip in addrs:
        reason = _ip_blocked(ip, cfg)
        if reason:
            raise UnsafeURLError(f"blocked_ip: {ip} ({reason}) for {host}")


async def safe_get(
    url: str,
    *,
    config: Optional[GuardConfig] = None,
    client: Optional[httpx.AsyncClient] = None,
    **kwargs: Any,
) -> httpx.Response:
    """``httpx.AsyncClient.get`` with the SSRF guard in front of it.

    When ``SAFE_FETCH_ENFORCE`` is off the guard logs but does not raise,
    matching the rollback contract.
    """
    try:
        assert_safe_url(url, config=config)
    except UnsafeURLError:
        if is_enforced():
            raise
    if client is not None:
        return await client.get(url, **kwargs)
    async with httpx.AsyncClient(timeout=kwargs.pop("timeout", 10.0),
                                 follow_redirects=False) as one_shot:
        return await one_shot.get(url, **kwargs)


async def safe_request(
    method: str,
    url: str,
    *,
    config: Optional[GuardConfig] = None,
    client: Optional[httpx.AsyncClient] = None,
    **kwargs: Any,
) -> httpx.Response:
    """Generic counterpart of :func:`safe_get` for non-GET verbs."""
    try:
        assert_safe_url(url, config=config)
    except UnsafeURLError:
        if is_enforced():
            raise
    if client is not None:
        return await client.request(method, url, **kwargs)
    async with httpx.AsyncClient(timeout=kwargs.pop("timeout", 10.0),
                                 follow_redirects=False) as one_shot:
        return await one_shot.request(method, url, **kwargs)


@dataclass(frozen=True)
class SafeFetchResult:
    """Outcome of a :func:`safe_follow_get` call."""

    status_code: int
    final_url: str
    body: str
    redirect_chain: tuple[str, ...]


async def safe_follow_get(
    url: str,
    *,
    config: Optional[GuardConfig] = None,
    timeout: float = 10.0,
    max_bytes: int = 256 * 1024,
    max_redirects: int = 3,
    headers: Optional[dict[str, str]] = None,
) -> SafeFetchResult:
    """GET ``url`` with manual redirect handling and per-hop SSRF revalidation.

    httpx's built-in ``follow_redirects=True`` is unsafe — a public host
    can return a 30x pointing at ``http://169.254.169.254/`` and httpx
    will happily fetch it. We disable httpx redirects and re-run
    :func:`assert_safe_url` against every ``Location`` before following.

    The body is read in chunks and truncated at ``max_bytes`` so a
    pathological 5 GB response can't exhaust memory. UTF-8 with replace
    fallback — these are best-effort scrapes, not protocol parsers.

    Always returns; non-2xx is reported via ``status_code``. Transport
    errors raise :class:`httpx.HTTPError`. Blocked URLs raise
    :class:`UnsafeURLError` when enforcement is on.
    """
    cfg = config or GuardConfig()
    chain: list[str] = []
    current = url
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers=headers or {},
    ) as client:
        for _hop in range(max_redirects + 1):
            try:
                assert_safe_url(current, config=cfg)
            except UnsafeURLError:
                if is_enforced():
                    raise
            chain.append(current)
            async with client.stream("GET", current) as resp:
                if 300 <= resp.status_code < 400 and "location" in resp.headers:
                    next_url = str(resp.headers["location"])
                    if next_url.startswith("/"):
                        # Relative redirect — resolve against current.
                        parsed = urlparse(current)
                        next_url = f"{parsed.scheme}://{parsed.netloc}{next_url}"
                    current = next_url
                    continue
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    if len(buf) + len(chunk) > max_bytes:
                        buf.extend(chunk[: max_bytes - len(buf)])
                        break
                    buf.extend(chunk)
                body_text = buf.decode("utf-8", errors="replace")
                return SafeFetchResult(
                    status_code=resp.status_code,
                    final_url=str(resp.url),
                    body=body_text,
                    redirect_chain=tuple(chain),
                )
    raise UnsafeURLError(f"too_many_redirects: >{max_redirects} for {url}")


__all__ = [
    "GuardConfig",
    "SafeFetchResult",
    "UnsafeURLError",
    "assert_safe_url",
    "is_enforced",
    "safe_follow_get",
    "safe_get",
    "safe_request",
]
