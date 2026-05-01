"""S17-P1 — EmailWriter: LLM-first with deterministic fallback templates."""
from __future__ import annotations

import logging
from typing import Any, Optional

from .personalization_scorer import _word_count, score_personalization
from .schemas import AskType, EmailDraft, OutreachContext

log = logging.getLogger(__name__)

_VALID_ASK_TYPES = {
    "referral", "coffee_chat", "advice", "info_interview", "reconnect",
}

_FALLBACK_CTA = {
    "referral": (
        "Would you be open to a brief intro to the hiring manager, or "
        "sharing how you decided {company} was the right fit?"
    ),
    "coffee_chat": (
        "Would you have 20 minutes for a virtual coffee in the next "
        "two weeks?"
    ),
    "advice": (
        "Would you have 15 minutes to share one piece of advice on "
        "navigating this?"
    ),
    "info_interview": (
        "Could I ask you 3 short questions about a day in your role, "
        "either by email or a 15-minute call?"
    ),
    "reconnect": (
        "Would love to catch up — does a short call in the next two "
        "weeks work?"
    ),
}

_FALLBACK_SUBJECT = {
    "referral": "Quick question about {company}",
    "coffee_chat": "20 minutes to learn from your path?",
    "advice": "One question on {role_short}",
    "info_interview": "Could I ask 3 questions about your role at {company}?",
    "reconnect": "Reconnecting — and a quick ask",
}


def _normalize_ask(ask_type: str) -> AskType:
    a = (ask_type or "").lower().strip()
    return a if a in _VALID_ASK_TYPES else "coffee_chat"


def _short_role(role: str) -> str:
    return (role or "your role").split(",")[0].strip() or "your role"


def _deterministic_body(ctx: OutreachContext, ask_type: AskType) -> str:
    first = (ctx.target_name or "there").split()[0]
    pitch = ctx.your_pitch or "I'm exploring my next step in this space"
    shared = (
        f" {ctx.shared_context.strip().rstrip('.')}." if ctx.shared_context
        else ""
    )
    company = ctx.target_company or "your company"
    cta = _FALLBACK_CTA[ask_type].format(company=company)

    opener = (
        f"Hi {first},\n\n"
        f"I'm {ctx.sender_name}"
        + (f", a {ctx.sender_role}" if ctx.sender_role else "")
        + ".{shared}".format(shared=shared)
    )
    middle = (
        f"\n\nI've been following the work you're doing"
        + (f" at {company}" if ctx.target_company else "")
        + f", and {pitch}. Your perspective on "
        f"{_short_role(ctx.target_role)} would be especially useful as I "
        "think about where to focus next."
    )
    close = f"\n\n{cta}\n\nThanks for considering it,\n{ctx.sender_name}"
    return opener + middle + close


def _deterministic_subject(ctx: OutreachContext, ask_type: AskType) -> str:
    return _FALLBACK_SUBJECT[ask_type].format(
        company=ctx.target_company or "your team",
        role_short=_short_role(ctx.target_role),
    )[:60]


class EmailWriter:
    """Generate a single outreach email draft.

    Tries the configured AIClient first; falls back to deterministic
    template if the LLM is unavailable, raises, or returns an
    incomplete payload.
    """

    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self._client = ai_client

    async def write(
        self,
        ctx: OutreachContext,
        ask_type: Optional[str] = None,
        tone: str = "warm",
    ) -> EmailDraft:
        if not ctx.sender_name or not ctx.target_name:
            raise ValueError("sender_name and target_name are required")
        a = _normalize_ask(ask_type or ctx.ask_type)

        subject = ""
        body = ""
        cta = ""

        if self._client is not None:
            try:
                payload = await self._client.complete_json(
                    prompt=self._build_prompt(ctx, a, tone),
                    system="Return strict JSON only.",
                    schema={
                        "type": "object",
                        "required": ["subject", "body"],
                        "properties": {
                            "subject": {"type": "string"},
                            "body": {"type": "string"},
                            "cta": {"type": "string"},
                        },
                    },
                    temperature=0.6,
                    task_type="networking_email",
                )
                if (
                    isinstance(payload, dict)
                    and payload.get("subject")
                    and payload.get("body")
                ):
                    subject = str(payload["subject"])[:80]
                    body = str(payload["body"]).strip()
                    cta = str(payload.get("cta", "")).strip()
            except Exception as exc:  # noqa: BLE001
                log.info("email_writer LLM failed, falling back: %s", exc)

        if not subject or not body:
            subject = _deterministic_subject(ctx, a)
            body = _deterministic_body(ctx, a)
            cta = _FALLBACK_CTA[a].format(
                company=ctx.target_company or "your team",
            )

        return EmailDraft(
            subject=subject,
            body=body,
            tone=tone,
            word_count=_word_count(body),
            personalization_score=score_personalization(body, ctx),
            cta=cta,
        )

    @staticmethod
    def _build_prompt(
        ctx: OutreachContext, ask_type: AskType, tone: str
    ) -> str:
        return (
            "Draft a short professional outreach email.\n"
            f"From: {ctx.sender_name} ({ctx.sender_role or 'job seeker'})\n"
            f"To: {ctx.target_name} — {ctx.target_role or 'unknown role'} "
            f"at {ctx.target_company or 'unknown company'}\n"
            f"Ask type: {ask_type}. Tone: {tone}. Word count 80-180.\n"
            f"Shared context: {ctx.shared_context or '(none)'}\n"
            f"Sender pitch: {ctx.your_pitch or '(none)'}\n"
            "Return JSON {subject, body, cta}. Subject under 60 chars. "
            "No fabricated facts. End with a clear ask."
        )
