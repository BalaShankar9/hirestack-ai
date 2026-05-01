"""S17-P1 — Sequence planner for outreach + follow-up cadence."""
from __future__ import annotations

from typing import Any, List, Optional

from .email_writer import EmailWriter, _normalize_ask
from .personalization_scorer import _word_count, score_personalization
from .schemas import EmailDraft, OutreachContext, OutreachSequence

_DEFAULT_CADENCE = [0, 5, 12]


def _follow_up_body(ctx: OutreachContext, idx: int) -> str:
    first = (ctx.target_name or "there").split()[0]
    if idx == 0:
        return (
            f"Hi {first},\n\n"
            "Bumping this in case it slipped past — totally understand "
            "if the timing isn't right. Happy to make it as easy as a "
            "single reply with a yes / no / not now.\n\n"
            f"Thanks,\n{ctx.sender_name}"
        )
    return (
        f"Hi {first},\n\n"
        "Closing the loop on my note from a couple weeks back. I'll stop "
        "reaching out after this so I'm not adding noise — but the door "
        "is open whenever the timing is better.\n\n"
        f"All the best,\n{ctx.sender_name}"
    )


def _follow_up_subject(initial_subject: str, idx: int) -> str:
    return (f"Re: {initial_subject}" if idx == 0 else f"Closing loop — {initial_subject}")[:80]


class SequencePlanner:
    """Build initial draft + N follow-ups with a sensible cadence."""

    def __init__(self, ai_client: Optional[Any] = None) -> None:
        self._writer = EmailWriter(ai_client=ai_client)

    async def plan(
        self,
        ctx: OutreachContext,
        follow_up_count: int = 2,
        cadence: Optional[List[int]] = None,
    ) -> OutreachSequence:
        if follow_up_count < 0:
            raise ValueError("follow_up_count must be >= 0")
        if follow_up_count > 4:
            follow_up_count = 4

        ask = _normalize_ask(ctx.ask_type)
        initial = await self._writer.write(ctx, ask_type=ask)

        follow_ups: List[EmailDraft] = []
        for i in range(follow_up_count):
            body = _follow_up_body(ctx, i)
            follow_ups.append(
                EmailDraft(
                    subject=_follow_up_subject(initial.subject, i),
                    body=body,
                    tone=initial.tone,
                    word_count=_word_count(body),
                    personalization_score=score_personalization(body, ctx),
                    cta="(soft bump)" if i == 0 else "(graceful close)",
                )
            )

        cad = list(cadence) if cadence else list(_DEFAULT_CADENCE)
        cad = cad[: 1 + follow_up_count]
        while len(cad) < 1 + follow_up_count:
            cad.append(cad[-1] + 7)

        rationale = [
            f"Ask type '{ask}' typically converts best with a 1-2 follow-up "
            "cadence; first bump after a business week, second after two.",
            "Each follow-up is shorter than the last and explicitly invites "
            "a 'no' to reduce social cost for the recipient.",
        ]
        return OutreachSequence(
            initial=initial,
            follow_ups=follow_ups,
            rationale=rationale,
            send_cadence_days=cad,
        )
