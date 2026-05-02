"""ATLAS Slice 4.1 — Streaming integration via emit_phase tests.

Verifies that CandidateFusion, ArchetypeGenerator, and
ValidationSwarm publish phase lifecycle events (`running` /
`completed` / `failed`) to the agent_events bus when an emitter is
bound, and stay silent / no-op when no emitter is bound (default).
"""
from __future__ import annotations

import asyncio
import contextvars
from typing import Any, Dict, List, Tuple

import pytest

from ai_engine import agent_events
from ai_engine.agents.artifact_contracts import (
    Archetype,
    CandidateProfile,
    CandidateSkill,
    CandidateValidationClaim,
    SkillProvenance,
)
from ai_engine.agents.sub_agents.atlas.dynamic_archetypes import ArchetypeGenerator
from ai_engine.agents.sub_agents.atlas.multi_source_fusion import CandidateFusion
from ai_engine.agents.sub_agents.atlas.validation_swarm import ValidationSwarm


def _run(coro):
    return asyncio.run(coro)


class _CapturingEmitter:
    """Bound as the active emitter; captures every (event_name, payload)."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Dict[str, Any]]] = []

    async def __call__(self, event_name: str, payload: Dict[str, Any]) -> None:
        self.events.append((event_name, dict(payload)))

    def phase_events(self):
        return [(p["phase"], p["status"]) for n, p in self.events if n == "phase"]


@pytest.fixture
def emitter():
    """Bind a fresh capturing emitter and unbind on teardown.

    NOTE: agent_events uses a ContextVar; in plain pytest tests
    (sync), set/reset must happen in the same context. The token
    cleanup runs in the same test thread so this works reliably.
    """
    cap = _CapturingEmitter()
    token = agent_events.set_event_emitter(cap)
    try:
        yield cap
    finally:
        agent_events.reset_event_emitter(token)


# ---------------------------------------------------------------------------
# CandidateFusion
# ---------------------------------------------------------------------------

def test_candidate_fusion_emits_running_and_completed(emitter):
    fusion = CandidateFusion()

    # CandidateFusion.fuse() is sync but emit_phase requires a
    # running asyncio loop (it schedules the emitter as a task). In
    # production the chain runs inside an async pipeline so a loop
    # is always present; here we mirror that by running fuse inside
    # an async wrapper.
    async def _go():
        result = fusion.fuse(
            candidate_name="Jane",
            resume_skills=["Python", "Go"],
        )
        # Yield once so the scheduled emitter task gets to run.
        await asyncio.sleep(0)
        return result

    _run(_go())

    phases = emitter.phase_events()
    assert ("candidate_fusion", "running") in phases
    assert ("candidate_fusion", "completed") in phases
    # Find the completed event and verify metadata
    completed = [p for n, p in emitter.events
                 if n == "phase" and p.get("phase") == "candidate_fusion"
                 and p.get("status") == "completed"][0]
    assert completed["agent"] == "atlas.candidate_fusion"
    # Note: emit_phase summarizes lists/dicts in metadata as
    # "<list len=N>" / "<dict len=N>" strings — see
    # ai_engine.agent_events._summarize. So we assert on shape.
    assert completed["metadata"]["skills"] >= 1
    assert "list len=" in str(completed["metadata"]["sources"])
    assert "latency_ms" in completed


def test_candidate_fusion_silent_without_emitter():
    """No emitter bound → fuse must still work, no exceptions."""
    fusion = CandidateFusion()
    profile = fusion.fuse(candidate_name="x", resume_skills=["Python"])
    assert isinstance(profile, CandidateProfile)


# ---------------------------------------------------------------------------
# ArchetypeGenerator
# ---------------------------------------------------------------------------

class _StubAIClientArche:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, **_kw):
        return self._payload


_VALID_ARCH_PAYLOAD = {
    "archetypes": [
        {
            "name": f"Arch {i}",
            "must_have_skills": ["python"],
            "nice_to_have_skills": [],
            "years_range": [3, 7],
            "salary_band": {},
            "cultural_signals": [],
        }
        for i in range(3)
    ]
}


def test_archetype_generator_emits_running_and_completed(emitter):
    gen = ArchetypeGenerator(_StubAIClientArche(_VALID_ARCH_PAYLOAD))
    out = _run(gen.generate(
        job_description="Senior Python role",
        role_target="senior_engineer",
        company_name="Acme",
        use_cache=False,
    ))
    assert len(out) == 3

    phases = emitter.phase_events()
    assert ("archetypes", "running") in phases
    assert ("archetypes", "completed") in phases

    completed = [p for n, p in emitter.events
                 if n == "phase" and p.get("phase") == "archetypes"
                 and p.get("status") == "completed"][0]
    assert completed["agent"] == "atlas.archetypes"
    assert completed["metadata"]["count"] == 3
    assert completed["metadata"]["cache_hit"] is False


def test_archetype_generator_emits_failed_on_llm_error(emitter):
    class _BoomClient:
        async def complete_json(self, **_kw):
            raise RuntimeError("LLM down")

    gen = ArchetypeGenerator(_BoomClient())
    out = _run(gen.generate(job_description="role", use_cache=False))
    assert out == []

    phases = emitter.phase_events()
    assert ("archetypes", "running") in phases
    assert ("archetypes", "failed") in phases


def test_archetype_generator_skips_emit_for_empty_jd(emitter):
    gen = ArchetypeGenerator(_StubAIClientArche(_VALID_ARCH_PAYLOAD))
    out = _run(gen.generate(job_description="", use_cache=False))
    assert out == []
    # Empty JD short-circuits before any emit
    assert emitter.phase_events() == []


def test_archetype_generator_emits_cache_hit(emitter):
    """Second call with same key should emit completed with cache_hit=True."""
    gen = ArchetypeGenerator(_StubAIClientArche(_VALID_ARCH_PAYLOAD))
    # Warm the cache.
    _run(gen.generate(
        job_description="JD body cache test",
        role_target="x", company_industry="y", use_cache=True,
    ))
    emitter.events.clear()
    # Second call should hit cache.
    _run(gen.generate(
        job_description="JD body cache test",
        role_target="x", company_industry="y", use_cache=True,
    ))
    completed = [p for n, p in emitter.events
                 if n == "phase" and p.get("phase") == "archetypes"
                 and p.get("status") == "completed"]
    assert any(c["metadata"].get("cache_hit") is True for c in completed)


# ---------------------------------------------------------------------------
# ValidationSwarm
# ---------------------------------------------------------------------------

class _StubValidator:
    def __init__(self, name: str, claims=None):
        self.name = name
        self._claims = claims or []

    async def validate(self, _profile):
        return list(self._claims)


def test_validation_swarm_emits_running_and_completed(emitter):
    gh = _StubValidator("github_commits")
    dt = _StubValidator("date_consistency", claims=[
        CandidateValidationClaim(
            claim="experience timeline coherent",
            validator="date_consistency",
            status="verified",
            detail="",
        ),
    ])
    co = _StubValidator("company_exists")
    swarm = ValidationSwarm(github_validator=gh, date_validator=dt, company_validator=co)

    profile = CandidateProfile(
        candidate_name="x",
        skills=[CandidateSkill(name="Python", provenance=[SkillProvenance(source="resume")])],
        sources_used=["resume"],
    )
    report = _run(swarm.validate(profile))
    assert report.verified_count == 1

    phases = emitter.phase_events()
    assert ("validation", "running") in phases
    assert ("validation", "completed") in phases

    completed = [p for n, p in emitter.events
                 if n == "phase" and p.get("phase") == "validation"
                 and p.get("status") == "completed"][0]
    assert completed["agent"] == "atlas.validation_swarm"
    assert completed["metadata"]["claims"] == 1
    assert completed["metadata"]["verified"] == 1
    assert completed["metadata"]["conflicted"] == 0
    assert "latency_ms" in completed


def test_validation_swarm_none_profile_no_emit(emitter):
    """None profile short-circuits before emit (preserves Slice 3.1 semantics)."""
    swarm = ValidationSwarm(
        github_validator=_StubValidator("github_commits"),
        date_validator=_StubValidator("date_consistency"),
        company_validator=_StubValidator("company_exists"),
    )
    rep = _run(swarm.validate(None))  # type: ignore[arg-type]
    assert rep.verified_count == 0
    # No emit at all for None profile
    assert emitter.phase_events() == []
