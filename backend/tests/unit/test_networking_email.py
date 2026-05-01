"""S17-P1 — Networking Email Generator tests."""
from __future__ import annotations

import pytest

from ai_engine.agents.networking import (
    EmailWriter,
    OutreachContext,
    SequencePlanner,
    build_networking_tools,
    detect_networking_intent,
    score_personalization,
)
from ai_engine.agents.networking.integration import draft_email, plan_sequence


# ─── stub LLM ───────────────────────────────────────────────────────

class _StubClient:
    def __init__(self, payload):
        self._payload = payload

    async def complete_json(self, **kwargs):
        return self._payload


class _RaisingClient:
    async def complete_json(self, **kwargs):
        raise RuntimeError("no llm")


def _ctx(**overrides) -> OutreachContext:
    base = dict(
        sender_name="Sam Iyer",
        sender_role="ML engineer transitioning to applied research",
        target_name="Jordan Park",
        target_role="Senior Research Scientist",
        target_company="Acme Labs",
        shared_context="We both went to Carnegie Mellon for the MSML program.",
        ask_type="coffee_chat",
        your_pitch="Working on retrieval-augmented evaluation pipelines",
    )
    base.update(overrides)
    return OutreachContext(**base)


# ─── intent ─────────────────────────────────────────────────────────

def test_intent_positive():
    assert detect_networking_intent("Help me draft a cold outreach email")
    assert detect_networking_intent("I want to write a coffee chat note")
    assert detect_networking_intent(
        "Email a recruiter to ask for a referral"
    )


def test_intent_negative():
    assert detect_networking_intent("How do I optimize my Postgres index?") is None
    assert detect_networking_intent("") is None


# ─── personalization scorer ────────────────────────────────────────

def test_personalization_scorer_rewards_specifics():
    ctx = _ctx()
    body = (
        "Hi Jordan,\n\nWe overlapped at Carnegie Mellon — the MSML "
        "program left a mark. I've been following your work at Acme "
        "Labs and your senior research perspective on retrieval "
        "evaluation would be incredibly useful as I think about my "
        "next step.\n\nWould you have 20 minutes for a virtual coffee "
        "in the next two weeks?\n\nThanks,\nSam"
    )
    assert score_personalization(body, ctx) >= 0.6


def test_personalization_scorer_penalizes_generic():
    ctx = _ctx()
    body = "Hey, let's connect. Would love to chat sometime!"
    assert score_personalization(body, ctx) < 0.3


# ─── email writer ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_email_writer_uses_llm_payload():
    payload = {
        "subject": "LLM SUBJECT",
        "body": (
            "Hi Jordan,\n\nWe both went to Carnegie Mellon. I'm Sam, "
            "working on retrieval evaluation at Acme Labs context. "
            "Would 20 minutes of your time work in the next two weeks?\n\n"
            "Thanks,\nSam"
        ),
        "cta": "20 minutes?",
    }
    draft = await EmailWriter(_StubClient(payload)).write(_ctx())
    assert draft.subject == "LLM SUBJECT"
    assert "Jordan" in draft.body
    assert draft.cta == "20 minutes?"
    assert draft.word_count > 0


@pytest.mark.asyncio
async def test_email_writer_falls_back_when_llm_raises():
    draft = await EmailWriter(_RaisingClient()).write(_ctx())
    assert draft.subject
    assert "Jordan" in draft.body
    assert draft.cta
    assert len(draft.subject) <= 60


@pytest.mark.asyncio
async def test_email_writer_normalizes_unknown_ask_type():
    draft = await EmailWriter(_RaisingClient()).write(_ctx(), ask_type="bogus")
    assert draft.cta  # default coffee_chat fallback CTA wired


@pytest.mark.asyncio
async def test_email_writer_rejects_missing_names():
    with pytest.raises(ValueError):
        await EmailWriter().write(
            OutreachContext(sender_name="", target_name="x")
        )


@pytest.mark.asyncio
async def test_email_writer_falls_back_when_llm_returns_garbage():
    draft = await EmailWriter(_StubClient({"subject": "", "body": ""})).write(_ctx())
    assert draft.subject
    assert draft.body


# ─── sequence planner ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sequence_planner_default_two_followups():
    seq = await SequencePlanner(_RaisingClient()).plan(_ctx())
    assert len(seq.follow_ups) == 2
    assert seq.send_cadence_days == [0, 5, 12]
    assert all(fu.body for fu in seq.follow_ups)
    assert all(len(fu.subject) <= 80 for fu in seq.follow_ups)


@pytest.mark.asyncio
async def test_sequence_planner_caps_followups_at_four():
    seq = await SequencePlanner(_RaisingClient()).plan(_ctx(), follow_up_count=99)
    assert len(seq.follow_ups) == 4
    assert len(seq.send_cadence_days) == 5


@pytest.mark.asyncio
async def test_sequence_planner_rejects_negative_count():
    with pytest.raises(ValueError):
        await SequencePlanner().plan(_ctx(), follow_up_count=-1)


# ─── e2e helpers ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draft_email_helper_e2e():
    d = await draft_email(ctx=_ctx().model_dump(), ask_type="referral")
    assert d.subject
    assert d.body


@pytest.mark.asyncio
async def test_plan_sequence_helper_e2e():
    s = await plan_sequence(ctx=_ctx().model_dump(), follow_up_count=1)
    assert len(s.follow_ups) == 1


# ─── tool registry ─────────────────────────────────────────────────

def test_build_networking_tools_registers_both():
    reg = build_networking_tools()
    assert reg.get("draft_outreach_email") is not None
    assert reg.get("plan_outreach_sequence") is not None
    assert "ctx" in reg.get("draft_outreach_email").parameters["required"]
