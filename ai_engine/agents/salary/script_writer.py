"""ScriptWriter — turn a NegotiationPlan into phone + email scripts.

Uses the AIClient when available; falls back to deterministic templates.
Tone selectable: collaborative | firm | warm.
"""
from __future__ import annotations

import logging
from typing import Optional

from ai_engine.agents.salary.schemas import (
    NegotiationPlan,
    NegotiationScript,
    OfferDetails,
)

logger = logging.getLogger("hirestack.salary.script")

_SCHEMA = {
    "type": "object",
    "properties": {
        "opening": {"type": "string"},
        "anchor": {"type": "string"},
        "silence_cue": {"type": "string"},
        "counter": {"type": "string"},
        "close": {"type": "string"},
        "talking_points": {"type": "array", "items": {"type": "string"}},
        "email_template": {"type": "string"},
    },
    "required": ["opening", "anchor", "counter", "close"],
}


def _safe_get_client():
    try:
        from ai_engine.client import get_ai_client
        return get_ai_client()
    except Exception as exc:  # noqa: BLE001
        logger.info("salary_script_no_client cause=%s", exc)
        return None


_TONE_VOCAB = {
    "collaborative": {
        "open_verb": "I'd love to talk through",
        "anchor_verb": "Based on market data, I was hoping we could land",
    },
    "firm": {
        "open_verb": "I want to discuss",
        "anchor_verb": "Given my market position, I need",
    },
    "warm": {
        "open_verb": "Thank you for the offer — I'd love to explore",
        "anchor_verb": "I really appreciate the offer; market data suggests",
    },
}


def _deterministic_script(
    offer: OfferDetails,
    plan: NegotiationPlan,
    tone: str,
) -> dict:
    vocab = _TONE_VOCAB.get(tone, _TONE_VOCAB["collaborative"])
    band = plan.market_band
    company = offer.company or "the team"
    counter_base = int(plan.counter_base)
    range_low = int(plan.target_range_low)
    range_high = int(plan.target_range_high)
    return {
        "opening": (
            f"Hi, thanks again for the offer. I'm excited about the role at "
            f"{company} and the team. {vocab['open_verb']} the compensation "
            "before I sign."
        ),
        "anchor": (
            f"{vocab['anchor_verb']} a base around ${counter_base:,}, which "
            f"reflects market data for {band.role.replace('_', ' ')} "
            f"({band.level}) in {band.location}: p50 around "
            f"${int(band.p50):,} and p75 around ${int(band.p75):,}."
        ),
        "silence_cue": (
            "After saying the number, stop talking. Count to seven slowly "
            "before adding anything. Let the silence land."
        ),
        "counter": (
            f"I'm targeting a base in the ${range_low:,}–${range_high:,} "
            "range. I'd love your help getting there — happy to discuss "
            "trade-offs across base, sign-on, or equity if that helps."
        ),
        "close": (
            "I want to make this work. Could you take this back to the "
            "hiring committee and let me know what's possible? I'll be "
            "ready to sign within 48 hours of an updated offer."
        ),
        "talking_points": [
            f"Market p75 for this role/level/location is ${int(band.p75):,}.",
            "I'm evaluating other opportunities and would prefer to land here.",
            "Open to creative structure: base / sign-on / equity / "
            "performance bonus.",
            "I can be available to start within two weeks of signing.",
        ],
        "email_template": (
            f"Subject: Following up on the offer for {offer.role}\n\n"
            f"Hi [Recruiter Name],\n\n"
            f"Thank you again for the offer to join {company} as a "
            f"{offer.role}. I'm excited about the team and the work.\n\n"
            f"After reviewing market data for this role and level, I'd love "
            f"to land at a base of ${counter_base:,}. This reflects the "
            f"p75 for {band.role.replace('_', ' ')} ({band.level}) in "
            f"{band.location} (${int(band.p75):,}) and aligns with the "
            "scope of impact we discussed.\n\n"
            "I'm flexible on structure — happy to talk through trade-offs "
            "across base, sign-on, and equity if that's useful. Could you "
            "let me know what's possible? I'll be ready to sign within 48 "
            "hours of an updated offer.\n\n"
            "Thanks,\n[Your Name]"
        ),
    }


class ScriptWriter:
    def __init__(self, *, ai_client=None):
        self._client = ai_client

    def _client_or_default(self):
        if self._client is None:
            self._client = _safe_get_client()
        return self._client

    async def write(
        self,
        offer: OfferDetails,
        plan: NegotiationPlan,
        *,
        tone: str = "collaborative",
    ) -> NegotiationScript:
        tone_norm = tone.lower() if tone else "collaborative"
        if tone_norm not in _TONE_VOCAB:
            tone_norm = "collaborative"

        client = self._client_or_default()
        payload: Optional[dict] = None
        if client is not None:
            try:
                payload = await client.complete_json(
                    prompt=self._prompt(offer, plan, tone_norm),
                    system="You are a senior career coach producing strict JSON.",
                    schema=_SCHEMA,
                    temperature=0.5,
                    task_type="salary_script",
                )
            except Exception as exc:  # noqa: BLE001
                logger.info("salary_script_llm_failed cause=%s", exc)
                payload = None

        if not isinstance(payload, dict) or "anchor" not in payload:
            payload = _deterministic_script(offer, plan, tone_norm)

        return NegotiationScript(
            tone=tone_norm,
            opening=(payload.get("opening") or "").strip(),
            anchor=(payload.get("anchor") or "").strip(),
            silence_cue=(payload.get("silence_cue") or "").strip(),
            counter=(payload.get("counter") or "").strip(),
            close=(payload.get("close") or "").strip(),
            talking_points=[
                str(p).strip() for p in (payload.get("talking_points") or [])
                if str(p).strip()
            ][:8],
            email_template=(payload.get("email_template") or "").strip(),
        )

    @staticmethod
    def _prompt(offer: OfferDetails, plan: NegotiationPlan, tone: str) -> str:
        band = plan.market_band
        return (
            f"Generate a salary-negotiation script in a {tone} tone.\n\n"
            f"OFFER: role={offer.role} level={offer.level} "
            f"location={offer.location} base=${int(offer.base):,} "
            f"bonus=${int(offer.bonus):,} equity=${int(offer.equity):,} "
            f"sign_on=${int(offer.sign_on):,} company={offer.company}\n"
            f"MARKET BAND ({band.source}): p25=${int(band.p25):,} "
            f"p50=${int(band.p50):,} p75=${int(band.p75):,} "
            f"p90=${int(band.p90):,}\n"
            f"PLAN: counter_base=${int(plan.counter_base):,} "
            f"target_range=${int(plan.target_range_low):,}-"
            f"${int(plan.target_range_high):,} "
            f"walk_away=${int(plan.walk_away):,}\n\n"
            "Return JSON with keys: opening, anchor, silence_cue, counter, "
            "close, talking_points (array), email_template."
        )
