"""
OfferAnalyzer — deterministic Phase 1 agent.

Parses offer details text to extract salary components, benefits,
and red flags.  No LLM call — pattern matching.
"""
from __future__ import annotations

import re

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


_RED_FLAG_PATTERNS: list[tuple[str, str]] = [
    ("no equity", "No equity offered — common in early-stage or non-tech companies"),
    ("no bonus", "No bonus structure mentioned"),
    ("contract", "Contract role — may lack benefits and job security"),
    ("probation", "Probationary period — ensure terms are reasonable"),
    ("non-compete", "Non-compete clause — review scope and duration carefully"),
    ("relocation required", "Relocation required — factor in moving costs"),
    ("below market", "Offer may be below market rate"),
    ("no remote", "No remote option — consider commute costs"),
    ("unlimited pto", "Unlimited PTO can mean less actual time off in practice"),
]

_POSITIVE_SIGNALS: list[tuple[str, str]] = [
    ("equity", "Equity/stock options included"),
    ("rsu", "RSU grant included"),
    ("stock", "Stock compensation included"),
    ("bonus", "Performance bonus included"),
    ("sign-on", "Sign-on bonus offered"),
    ("signing bonus", "Signing bonus offered"),
    ("remote", "Remote work option available"),
    ("flexible", "Flexible work arrangement"),
    ("401k match", "401k match benefit"),
    ("pension", "Pension contribution"),
    ("learning", "Learning & development budget"),
    ("education", "Education reimbursement"),
]


class OfferAnalyzer(SubAgent):
    """Parses offer details and identifies red flags and positives."""

    def __init__(self, ai_client=None):
        super().__init__(name="offer_analyzer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        offer_text: str = (context.get("offer_details") or "").lower()

        has_offer = offer_text and offer_text not in ("no offer yet", "not specified", "n/a", "none")

        red_flags: list[str] = []
        positives: list[str] = []

        if has_offer:
            for pattern, message in _RED_FLAG_PATTERNS:
                if pattern in offer_text:
                    red_flags.append(message)
            for pattern, message in _POSITIVE_SIGNALS:
                if pattern in offer_text:
                    positives.append(message)

            # Extract any numeric salary from offer
            salary_match = re.search(r'[\$£€]?\s*([\d,]+)\s*(?:k|K)?', offer_text)
            offer_salary = None
            if salary_match:
                raw = salary_match.group(1).replace(",", "")
                if raw.isdigit():
                    val = int(raw)
                    offer_salary = val * 1000 if val < 1000 else val
        else:
            offer_salary = None

        return SubAgentResult(
            agent_name=self.name,
            data={
                "has_offer": has_offer,
                "offer_salary_extracted": offer_salary,
                "red_flags": red_flags[:8],
                "positive_signals": positives[:8],
                "red_flag_count": len(red_flags),
                "positive_count": len(positives),
            },
            confidence=0.80 if has_offer else 0.50,
        )
