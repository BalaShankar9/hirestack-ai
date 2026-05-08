# backend/tests/unit/test_anthropic_provider.py
"""Tests for the Anthropic provider (PR m7-pr28, ADR-0031).

The ``anthropic`` SDK is mocked end-to-end so the suite never reaches the
network and does not require ``ANTHROPIC_API_KEY`` / the ``anthropic``
package to be installed in the test environment.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ─── Helpers ────────────────────────────────────────────────────────────

def _install_fake_anthropic(messages_create=None, stream_chunks=None,
                            stream_raises: Exception | None = None) -> MagicMock:
    """Insert a stand-in ``anthropic`` module exposing ``Anthropic``.

    Returns the constructed client mock so tests can introspect calls.
    """
    fake_module = types.ModuleType("anthropic")
    client_mock = MagicMock()

    if messages_create is not None:
        client_mock.messages.create.side_effect = messages_create

    # Streaming context manager
    class _StreamCtx:
        def __init__(self, chunks, raises):
            self._chunks = list(chunks or [])
            self._raises = raises
            self.text_stream = self._iter()

        def _iter(self):
            if self._raises is not None:
                raise self._raises
            for c in self._chunks:
                yield c

        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _stream(**kwargs):
        return _StreamCtx(stream_chunks, stream_raises)

    client_mock.messages.stream.side_effect = _stream

    AnthropicCls = MagicMock(return_value=client_mock)
    fake_module.Anthropic = AnthropicCls
    sys.modules["anthropic"] = fake_module
    return client_mock


def _msg(text: str) -> MagicMock:
    """Build an anthropic Message-like response with one text block."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


@pytest.fixture(autouse=True)
def _stub_settings():
    with patch("ai_engine.client.settings") as s:
        s.anthropic_api_key = "test-key"
        s.anthropic_default_model = "claude-3-5-sonnet-20241022"
        s.anthropic_max_tokens = 1024
        # Gemini settings still needed for module init paths
        s.gemini_model = "gemini-2.5-flash"
        s.gemini_max_tokens = 8192
        s.gemini_api_key = "test-key"
        s.gemini_use_vertexai = False
        yield s


# ─── Tests ──────────────────────────────────────────────────────────────

class TestAnthropicProvider:
    @pytest.mark.asyncio
    async def test_complete_round_trip(self):
        client = _install_fake_anthropic(
            messages_create=lambda **kw: _msg("hello world"),
        )
        from ai_engine.client import _AnthropicProvider
        provider = _AnthropicProvider()
        out = await provider.complete(prompt="hi", model="claude-3-5-sonnet-20241022")
        assert out == "hello world"
        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["model"] == "claude-3-5-sonnet-20241022"
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]

    @pytest.mark.asyncio
    async def test_complete_json_strips_markdown_fences(self):
        _install_fake_anthropic(
            messages_create=lambda **kw: _msg("```json\n{\"k\": \"v\"}\n```"),
        )
        from ai_engine.client import _AnthropicProvider
        provider = _AnthropicProvider()
        out = await provider.complete_json(prompt="x")
        assert out == {"k": "v"}

    @pytest.mark.asyncio
    async def test_complete_json_appends_json_only_instruction(self):
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return _msg("{}")

        _install_fake_anthropic(messages_create=_capture)
        from ai_engine.client import _AnthropicProvider
        provider = _AnthropicProvider()
        await provider.complete_json(prompt="x", system="be helpful")
        assert "Respond ONLY with valid JSON" in captured["system"]
        assert "be helpful" in captured["system"]

    @pytest.mark.asyncio
    async def test_chat_passes_messages_through(self):
        captured = {}

        def _capture(**kwargs):
            captured.update(kwargs)
            return _msg("ack")

        _install_fake_anthropic(messages_create=_capture)
        from ai_engine.client import _AnthropicProvider
        provider = _AnthropicProvider()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "again"},
        ]
        out = await provider.chat(messages=msgs, system="sys")
        assert out == "ack"
        assert captured["messages"] == msgs
        assert captured["system"] == "sys"

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self, _stub_settings):
        _stub_settings.anthropic_api_key = ""
        _install_fake_anthropic(messages_create=lambda **kw: _msg("x"))
        from ai_engine.client import _AnthropicProvider
        provider = _AnthropicProvider()
        # Validate at the lazy-init seam (avoids tenacity's exponential
        # retry on a config error that will never resolve mid-flight).
        with pytest.raises(ValueError, match="Anthropic API key"):
            provider._get_client()

    @pytest.mark.asyncio
    async def test_stream_completion_yields_deltas(self):
        _install_fake_anthropic(stream_chunks=["he", "llo", " world"])
        from ai_engine.client import _AnthropicProvider
        provider = _AnthropicProvider()
        out = []
        async for chunk in provider.stream_completion(prompt="hi"):
            out.append(chunk)
        assert out == ["he", "llo", " world"]

    @pytest.mark.asyncio
    async def test_complete_json_streaming_calls_token_sink_per_chunk(self):
        _install_fake_anthropic(stream_chunks=["{\"k\":", " \"v\"", "}"])
        from ai_engine.client import _AnthropicProvider
        provider = _AnthropicProvider()
        seen = []

        async def sink(chunk):
            seen.append(chunk)

        out = await provider.complete_json_streaming(prompt="x", token_sink=sink)
        assert out == {"k": "v"}
        assert seen == ["{\"k\":", " \"v\"", "}"]
