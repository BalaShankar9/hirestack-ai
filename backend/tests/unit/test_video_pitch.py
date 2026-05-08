"""S17-P4 — Executive Video Pitch tests."""
from __future__ import annotations

import pytest

from ai_engine.agents.video_pitch import (
    HeyGenProvider,
    PitchOrchestrator,
    ScriptWriter,
    StubProvider,
    VideoPitchInput,
    build_video_pitch_tools,
    create_video_pitch,
    detect_video_pitch_intent,
    get_provider,
)
from ai_engine.agents.orchestration import VIDEO_PITCH_PHASE_ORDER


# ─── stub LLM ──────────────────────────────────────────────────────

class _StubClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    async def complete_json(self, **kwargs):
        self.calls += 1
        return self._payload


class _RaisingClient:
    async def complete_json(self, **kwargs):
        raise RuntimeError("no llm")


# ─── HTTP stub for HeyGen ─────────────────────────────────────────

class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _HttpClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def post(self, url, headers=None, json=None, **kw):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._response

    async def aclose(self):
        pass


# ─── helpers ───────────────────────────────────────────────────────

def _sample_input(**overrides) -> VideoPitchInput:
    base = dict(
        candidate_name="Grace Hopper",
        role_target="VP of Engineering",
        value_prop="I scale teams that ship reliably under load.",
        key_wins=[
            "Led 4x platform throughput improvement",
            "Built compiler that became industry standard",
        ],
        duration_seconds=45,
        avatar_style="executive",
    )
    base.update(overrides)
    return VideoPitchInput(**base)


# ─── intent ────────────────────────────────────────────────────────

def test_intent_positive():
    assert detect_video_pitch_intent("Generate a video pitch for me")
    assert detect_video_pitch_intent("Create an executive pitch with avatar")


def test_intent_negative():
    assert detect_video_pitch_intent("Write a cover letter") is None
    assert detect_video_pitch_intent("") is None


# ─── script writer ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_script_writer_fallback_uses_inputs():
    script = await ScriptWriter().write(_sample_input())
    assert "Grace Hopper" in script.intro
    assert "VP of Engineering" in script.hook
    assert len(script.key_points) >= 1
    assert script.cta
    assert script.total_word_count > 10


@pytest.mark.asyncio
async def test_script_writer_uses_llm_payload():
    payload = {
        "intro": "I'm Grace, ex-Navy, ex-Eckert-Mauchly.",
        "hook": "I want the VP role because compilers are my craft.",
        "key_points": ["scaled team 5x", "shipped COBOL"],
        "cta": "Let's talk Tuesday.",
    }
    client = _StubClient(payload)
    script = await ScriptWriter(ai_client=client).write(_sample_input())
    assert client.calls == 1
    assert script.intro.startswith("I'm Grace")
    assert script.key_points == ["scaled team 5x", "shipped COBOL"]


@pytest.mark.asyncio
async def test_script_writer_falls_back_when_llm_raises():
    script = await ScriptWriter(ai_client=_RaisingClient()).write(_sample_input())
    assert "Grace Hopper" in script.intro


@pytest.mark.asyncio
async def test_script_writer_falls_back_on_garbage_payload():
    script = await ScriptWriter(ai_client=_StubClient({"intro": ""})).write(
        _sample_input()
    )
    assert "Grace Hopper" in script.intro


@pytest.mark.asyncio
async def test_script_writer_rejects_blank_required_fields():
    with pytest.raises(ValueError):
        await ScriptWriter().write(_sample_input(candidate_name="  "))
    with pytest.raises(ValueError):
        await ScriptWriter().write(_sample_input(role_target="  "))


# ─── providers ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stub_provider_is_deterministic():
    inp = _sample_input()
    s = await ScriptWriter().write(inp)
    a = await StubProvider().submit(script=s, style=inp.avatar_style)
    b = await StubProvider().submit(script=s, style=inp.avatar_style)
    assert a.avatar_id == b.avatar_id
    assert a.status == "queued"
    assert a.provider == "stub"


@pytest.mark.asyncio
async def test_heygen_missing_key_returns_failed():
    inp = _sample_input()
    s = await ScriptWriter().write(inp)
    p = HeyGenProvider(api_key="")
    manifest = await p.submit(script=s, style=inp.avatar_style)
    assert manifest.status == "failed"
    assert "HEYGEN" in (manifest.error or "")


@pytest.mark.asyncio
async def test_heygen_success_returns_queued():
    inp = _sample_input()
    s = await ScriptWriter().write(inp)
    http = _HttpClient(_Resp(200, {"data": {"video_id": "vid-123"}}))
    p = HeyGenProvider(api_key="abc", client=http)
    manifest = await p.submit(script=s, style=inp.avatar_style)
    assert manifest.status == "queued"
    assert manifest.job_id == "vid-123"
    assert http.calls and "heygen.com" in http.calls[0]["url"]


@pytest.mark.asyncio
async def test_heygen_http_error_returns_failed():
    inp = _sample_input()
    s = await ScriptWriter().write(inp)
    http = _HttpClient(_Resp(500, {}))
    p = HeyGenProvider(api_key="abc", client=http)
    manifest = await p.submit(script=s, style=inp.avatar_style)
    assert manifest.status == "failed"
    assert "500" in (manifest.error or "")


def test_get_provider_default_is_stub(monkeypatch):
    monkeypatch.delenv("VIDEO_AVATAR_PROVIDER", raising=False)
    assert isinstance(get_provider(), StubProvider)


def test_get_provider_heygen(monkeypatch):
    monkeypatch.setenv("VIDEO_AVATAR_PROVIDER", "heygen")
    assert isinstance(get_provider(), HeyGenProvider)


# ─── orchestrator + e2e ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_returns_full_package_with_stub_provider():
    pkg = await PitchOrchestrator(provider=StubProvider()).create(_sample_input())
    assert pkg.script.total_word_count > 0
    assert pkg.manifest.provider == "stub"
    assert pkg.audio_b64 is None
    assert pkg.latency_ms >= 0
    assert pkg.workflow_id
    assert tuple(pkg.phase_latencies.keys()) == VIDEO_PITCH_PHASE_ORDER[:2]
    assert pkg.phase_statuses == {
        "script_write": "completed",
        "avatar_submit": "completed",
    }


class _StubTTS:
    async def synthesize(self, text):
        return b"a" * 256 if text else None


@pytest.mark.asyncio
async def test_orchestrator_records_audio_phase_when_audio_requested():
    pkg = await PitchOrchestrator(
        provider=StubProvider(),
        tts=_StubTTS(),
    ).create(_sample_input(include_audio=True))

    assert pkg.audio_b64 is not None
    assert "tts_synthesize" in pkg.phase_latencies
    assert tuple(pkg.phase_latencies.keys()) == VIDEO_PITCH_PHASE_ORDER
    assert pkg.phase_statuses["tts_synthesize"] == "completed"


@pytest.mark.asyncio
async def test_create_video_pitch_helper_accepts_dict():
    pkg = await create_video_pitch({
        "candidate_name": "Ada", "role_target": "Lead Eng",
    })
    assert pkg.script.intro
    assert pkg.manifest.status == "queued"


# ─── tool registry ────────────────────────────────────────────────

def test_build_video_pitch_tools_registers():
    reg = build_video_pitch_tools()
    tool = reg.get("create_executive_video_pitch")
    assert tool is not None
    assert "input" in tool.parameters["required"]
