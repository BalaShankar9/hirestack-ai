"""S7-F3: pin app/services/social_connector.py contracts.

Behavioural lock for the URL parsing + SSRF block list. These are
the security-critical pure surfaces of SocialConnector — every test
runs without httpx (we never call .connect() with a real host).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.social_connector import CONNECT_TIMEOUT, SocialConnector


# ── _extract_github_username ──────────────────────────────────────


class TestExtractGithubUsername:
    @pytest.fixture
    def conn(self):
        return SocialConnector()

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/octocat", "octocat"),
            ("http://github.com/octocat/", "octocat"),
            ("github.com/octocat", "octocat"),
            ("https://github.com/some-user", "some-user"),
            ("https://github.com/user_name", "user_name"),
            ("https://github.com/User123", "User123"),
            ("octocat", "octocat"),  # plain handle
            ("user-name_123", "user-name_123"),
        ],
    )
    def test_valid_extractions(self, conn, url, expected):
        assert conn._extract_github_username(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/user/repo",  # path past username
            "https://github.com/",  # empty
            "https://github.com",  # no slash
            "user/with/slash",
            "user with space",
            "user@with#chars",
            "",
        ],
    )
    def test_invalid_extractions_return_none(self, conn, url):
        assert conn._extract_github_username(url) is None


# ── _extract_html_tag ─────────────────────────────────────────────


class TestExtractHtmlTag:
    @pytest.fixture
    def conn(self):
        return SocialConnector()

    def test_simple_title_extracted(self, conn):
        assert conn._extract_html_tag("<title>Hello</title>", "title") == "Hello"

    def test_case_insensitive_tag_match(self, conn):
        assert conn._extract_html_tag("<TITLE>Hi</TITLE>", "title") == "Hi"

    def test_attributes_on_open_tag_ok(self, conn):
        assert conn._extract_html_tag('<title id="x">Hello</title>', "title") == "Hello"

    def test_inner_whitespace_stripped(self, conn):
        assert conn._extract_html_tag("<title>  spaced  </title>", "title") == "spaced"

    def test_missing_tag_returns_none(self, conn):
        assert conn._extract_html_tag("<body>x</body>", "title") is None

    def test_dotall_match_for_multiline(self, conn):
        # Pattern uses re.DOTALL — newlines inside the tag body are fine.
        html = "<title>line1\nline2</title>"
        out = conn._extract_html_tag(html, "title")
        assert "line1" in out and "line2" in out


# ── _extract_meta ─────────────────────────────────────────────────


class TestExtractMeta:
    @pytest.fixture
    def conn(self):
        return SocialConnector()

    def test_name_attribute_form(self, conn):
        html = '<meta name="description" content="hello">'
        assert conn._extract_meta(html, "description") == "hello"

    def test_property_attribute_form(self, conn):
        html = '<meta property="og:title" content="Some Title">'
        assert conn._extract_meta(html, "og:title") == "Some Title"

    def test_reversed_attribute_order(self, conn):
        html = '<meta content="Reversed" name="description">'
        assert conn._extract_meta(html, "description") == "Reversed"

    def test_single_quote_attributes(self, conn):
        html = "<meta name='description' content='single'>"
        assert conn._extract_meta(html, "description") == "single"

    def test_missing_meta_returns_none(self, conn):
        assert conn._extract_meta("<head></head>", "description") is None

    def test_case_insensitive(self, conn):
        html = '<META NAME="Description" CONTENT="upper">'
        assert conn._extract_meta(html, "description") == "upper"


# ── connect() dispatcher ──────────────────────────────────────────


class TestConnectDispatcher:
    @pytest.mark.asyncio
    async def test_empty_url_raises(self):
        conn = SocialConnector()
        with pytest.raises(ValueError, match="URL is required"):
            await conn.connect("github", "")

    @pytest.mark.asyncio
    async def test_whitespace_only_url_raises(self):
        conn = SocialConnector()
        with pytest.raises(ValueError, match="URL is required"):
            await conn.connect("github", "   ")

    @pytest.mark.asyncio
    async def test_unknown_platform_raises(self):
        conn = SocialConnector()
        with pytest.raises(ValueError, match="Unsupported platform"):
            await conn.connect("myspace", "https://example.com")

    @pytest.mark.asyncio
    async def test_known_platforms_route(self):
        # Confirm dispatcher routes to the right private method.
        # Each branch's private impl is patched with a sentinel.
        conn = SocialConnector()
        sentinel = {"status": "patched"}

        async def fake(*a, **kw):
            return sentinel

        with patch.object(conn, "_connect_github", side_effect=fake) as gh, \
             patch.object(conn, "_connect_linkedin", side_effect=fake) as li, \
             patch.object(conn, "_connect_website", side_effect=fake) as ws, \
             patch.object(conn, "_connect_twitter", side_effect=fake) as tw:
            assert (await conn.connect("github", "https://github.com/x")) is sentinel
            assert gh.called
            assert (await conn.connect("linkedin", "https://linkedin.com/in/x")) is sentinel
            assert li.called
            assert (await conn.connect("website", "https://example.com")) is sentinel
            assert ws.called
            assert (await conn.connect("twitter", "https://x.com/x")) is sentinel
            assert tw.called


# ── _connect_twitter (no I/O) ─────────────────────────────────────


class TestConnectTwitter:
    @pytest.mark.asyncio
    async def test_twitter_url_extracts_handle(self):
        conn = SocialConnector()
        out = await conn._connect_twitter("https://twitter.com/jack")
        assert out["status"] == "linked"
        assert out["data"]["handle"] == "jack"
        assert out["data"]["url"] == "https://x.com/jack"
        assert out["data"]["method"] == "url_verified"

    @pytest.mark.asyncio
    async def test_x_url_extracts_handle(self):
        conn = SocialConnector()
        out = await conn._connect_twitter("https://x.com/elonmusk")
        assert out["data"]["handle"] == "elonmusk"
        assert out["data"]["url"] == "https://x.com/elonmusk"

    @pytest.mark.asyncio
    async def test_plain_handle_with_at(self):
        conn = SocialConnector()
        out = await conn._connect_twitter("@jack")
        assert out["data"]["handle"] == "jack"

    @pytest.mark.asyncio
    async def test_plain_handle_without_at(self):
        conn = SocialConnector()
        out = await conn._connect_twitter("jack")
        assert out["data"]["handle"] == "jack"

    @pytest.mark.asyncio
    async def test_invalid_url_raises(self):
        conn = SocialConnector()
        with pytest.raises(ValueError, match="Invalid Twitter/X URL"):
            await conn._connect_twitter("https://example.com/jack")

    @pytest.mark.asyncio
    async def test_returns_iso_timestamp(self):
        conn = SocialConnector()
        out = await conn._connect_twitter("@jack")
        assert "T" in out["connected_at"]  # ISO format


# ── _connect_linkedin (no I/O when profile_data absent) ───────────


class TestConnectLinkedin:
    @pytest.mark.asyncio
    async def test_valid_url_no_profile_data(self):
        conn = SocialConnector()
        out = await conn._connect_linkedin("https://linkedin.com/in/john-doe")
        assert out["status"] == "connected"
        assert out["data"]["slug"] == "john-doe"
        assert out["data"]["method"] == "ai_analysis"
        assert "analysis" not in out["data"]  # no profile data → no AI call

    @pytest.mark.asyncio
    async def test_invalid_url_raises(self):
        conn = SocialConnector()
        with pytest.raises(ValueError, match="Invalid LinkedIn URL"):
            await conn._connect_linkedin("https://example.com/in/foo")

    @pytest.mark.asyncio
    async def test_url_without_in_segment_raises(self):
        conn = SocialConnector()
        with pytest.raises(ValueError, match="Invalid LinkedIn URL"):
            await conn._connect_linkedin("https://linkedin.com/company/foo")


# ── _connect_website SSRF guard (CRITICAL) ────────────────────────


class TestConnectWebsiteSsrf:
    """Pin the SSRF block list. Each test triggers DNS resolution
    via socket.getaddrinfo (patched) to feed a deterministic IP into
    the guard, then asserts the guard raises ValueError BEFORE
    httpx is ever touched.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",          # IPv4 loopback
            "127.255.255.254",    # any 127/8
            "10.0.0.1",           # RFC1918
            "10.255.255.255",
            "172.16.0.1",         # RFC1918
            "172.31.255.255",
            "192.168.1.1",        # RFC1918
            "169.254.169.254",    # AWS metadata!
            "169.254.0.1",        # link-local
        ],
    )
    async def test_blocked_ipv4(self, ip):
        conn = SocialConnector()
        # getaddrinfo returns a list of (family, type, proto, canonname, sockaddr).
        # SocialConnector reads sockaddr[0] and feeds it to ip_address().
        with patch(
            "socket.getaddrinfo",
            return_value=[(2, 1, 6, "", (ip, 443))],
        ):
            with pytest.raises(ValueError, match="private/internal"):
                await conn._connect_website("https://evil.example.com")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "ip",
        [
            "::1",            # IPv6 loopback
            "fc00::1",        # IPv6 ULA
            "fdff::1",        # also fc00::/7
        ],
    )
    async def test_blocked_ipv6(self, ip):
        conn = SocialConnector()
        with patch(
            "socket.getaddrinfo",
            return_value=[(10, 1, 6, "", (ip, 443, 0, 0))],
        ):
            with pytest.raises(ValueError, match="private/internal"):
                await conn._connect_website("https://evil.example.com")

    @pytest.mark.asyncio
    async def test_dns_failure_raises_value_error(self):
        conn = SocialConnector()
        import socket as _socket

        with patch(
            "socket.getaddrinfo",
            side_effect=_socket.gaierror("nope"),
        ):
            with pytest.raises(ValueError, match="Could not resolve hostname"):
                await conn._connect_website("https://no-such-host.invalid")

    @pytest.mark.asyncio
    async def test_invalid_url_no_hostname_raises(self):
        conn = SocialConnector()
        with pytest.raises(ValueError, match="Invalid URL"):
            # urlparse("https://").hostname is None → guard fires.
            await conn._connect_website("https://")

    @pytest.mark.asyncio
    async def test_url_gets_https_prefix_when_missing(self):
        # The implementation prepends "https://" if neither scheme is
        # present. We verify by patching getaddrinfo to a public IP
        # and intercepting httpx — but easier: trigger the SSRF
        # block on a private IP and confirm hostname was parsed.
        conn = SocialConnector()
        with patch(
            "socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("10.0.0.1", 443))],
        ):
            with pytest.raises(ValueError, match="private/internal"):
                # Note: NO scheme; implementation must prepend it
                # before urlparse, otherwise this would fail with
                # "Invalid URL".
                await conn._connect_website("example.com")


# ── Module constants ──────────────────────────────────────────────


class TestConstants:
    def test_connect_timeout_reasonable(self):
        # Pin the 15s timeout — operators rely on this for SLOs.
        assert CONNECT_TIMEOUT == 15
