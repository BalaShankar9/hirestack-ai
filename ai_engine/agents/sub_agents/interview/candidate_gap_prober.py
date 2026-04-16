"""
CandidateGapProber — deterministic Phase 1 agent.

Identifies mismatches between JD requirements and candidate profile
to generate targeted probe areas for interview questions.
No LLM call — set-based comparison.
"""
from __future__ import annotations

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult


class CandidateGapProber(SubAgent):
    """Identifies skill/experience gaps to probe during interview."""

    def __init__(self, ai_client=None):
        super().__init__(name="candidate_gap_prober", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        jd_summary: str = (context.get("jd_summary") or "").lower()
        profile_summary: str = (context.get("profile_summary") or "").lower()
        job_title: str = context.get("job_title", "")

        # Leverage Phase 1 peer data if available (from RoleContextExtractor)
        role_ctx = context.get("_role_context", {})
        jd_skills: list[str] = role_ctx.get("jd_skills", [])
        profile_skills: list[str] = role_ctx.get("profile_skills", [])

        # ── Skill gaps: in JD but not in profile ───────────────
        jd_set = set(jd_skills) if jd_skills else set()
        profile_set = set(profile_skills) if profile_skills else set()
        missing_skills = sorted(jd_set - profile_set)

        # ── Experience probes ──────────────────────────────────
        probes: list[dict[str, str]] = []
        for skill in missing_skills[:8]:
            probes.append({
                "area": skill,
                "probe_type": "technical_depth",
                "reason": f"'{skill}' appears in JD but not in candidate profile",
            })

        # ── Responsibility-based probes ────────────────────────
        responsibility_signals = [
            ("team lead", "leadership", "How they've led teams or projects"),
            ("architect", "system_design", "Whether they can design complex systems"),
            ("mentor", "mentorship", "Ability to mentor and grow others"),
            ("cross-functional", "collaboration", "Working across team boundaries"),
            ("stakeholder", "communication", "Managing stakeholder expectations"),
            ("budget", "business_acumen", "Experience with budget/resource decisions"),
        ]
        for signal, probe_type, reason in responsibility_signals:
            if signal in jd_summary and signal not in profile_summary:
                probes.append({
                    "area": signal,
                    "probe_type": probe_type,
                    "reason": reason,
                })

        # Cap probes
        probes = probes[:12]

        return SubAgentResult(
            agent_name=self.name,
            data={
                "missing_skills": missing_skills,
                "probes": probes,
                "gap_count": len(missing_skills),
                "probe_count": len(probes),
            },
            confidence=0.80,
        )
