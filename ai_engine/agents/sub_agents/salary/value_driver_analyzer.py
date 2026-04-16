"""
ValueDriverAnalyzer — deterministic Phase 1 agent.

Identifies candidate value drivers (skills, certs, experience) and
detractors (gaps, career breaks) from profile data.  No LLM call.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


_HIGH_VALUE_SKILLS = {
    "machine learning", "deep learning", "llm", "kubernetes", "go", "rust",
    "system design", "distributed systems", "aws", "gcp", "azure",
    "typescript", "react", "python", "security", "data engineering",
}

_HIGH_VALUE_CERTS = {
    "aws certified", "gcp certified", "azure certified", "cka", "ckad",
    "cissp", "pmp", "scrum master", "terraform associate",
}


class ValueDriverAnalyzer(SubAgent):
    """Identifies candidate value drivers and detractors."""

    def __init__(self, ai_client=None):
        super().__init__(name="value_driver_analyzer", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        skills_summary: str = (context.get("skills_summary") or "").lower()
        years: int = context.get("years_experience", 0)
        current_salary: str = context.get("current_salary", "")
        target_salary: str = context.get("target_salary", "")

        # ── Value drivers ─────────────────────────────────────
        drivers: list[str] = []

        for skill in _HIGH_VALUE_SKILLS:
            if skill in skills_summary:
                drivers.append(f"In-demand skill: {skill}")
        if len(drivers) < 2:
            drivers.append("Demonstrated career progression")

        for cert in _HIGH_VALUE_CERTS:
            if cert in skills_summary:
                drivers.append(f"Valuable certification: {cert}")

        if years >= 8:
            drivers.append(f"Significant experience ({years} years)")
        elif years >= 5:
            drivers.append(f"Solid experience ({years} years)")

        # ── Detractors ────────────────────────────────────────
        detractors: list[str] = []

        if years < 2:
            detractors.append("Limited professional experience")

        # Check for salary mismatch signals
        curr_num = self._parse_salary(current_salary)
        tgt_num = self._parse_salary(target_salary)
        if curr_num and tgt_num and tgt_num > curr_num * 1.5:
            detractors.append(f"Large salary jump requested (~{int((tgt_num/curr_num - 1)*100)}% increase)")

        if not drivers:
            detractors.append("No standout differentiators identified from profile")

        # ── Salary leverage score (0-100) ─────────────────────
        leverage = min(100, 30 + len(drivers) * 10 + years * 2)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "key_value_drivers": drivers[:8],
                "value_detractors": detractors[:5],
                "leverage_score": leverage,
                "driver_count": len(drivers),
            },
            confidence=0.75,
        )

    @staticmethod
    def _parse_salary(text: str) -> int | None:
        """Extract a numeric salary from text like '$120,000' or '120000'."""
        if not text:
            return None
        cleaned = text.replace(",", "").replace("$", "").replace("£", "").replace("€", "")
        digits = "".join(c for c in cleaned if c.isdigit())
        if digits and len(digits) >= 4:
            return int(digits)
        return None
