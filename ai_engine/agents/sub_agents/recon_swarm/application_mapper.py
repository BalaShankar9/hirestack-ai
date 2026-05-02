"""S18 — Application Mapper: turn CompanyIntelV2 → ApplicationKit.

Pure-python deterministic synthesis. No LLM in this path — the kit is
generated mechanically from intel fields + candidate skills/values so
unit tests stay stable. Document chains can polish later.
"""
from __future__ import annotations

from typing import List, Optional

from .schemas import ApplicationKit, CompanyIntelV2


class ApplicationMapper:
    @staticmethod
    def _norm(s: str) -> str:
        return (s or "").strip().lower()

    def map(
        self,
        intel: CompanyIntelV2,
        *,
        role_target: Optional[str] = None,
        candidate_skills: Optional[List[str]] = None,
        candidate_values: Optional[List[str]] = None,
    ) -> ApplicationKit:
        candidate_skills = candidate_skills or []
        candidate_values = candidate_values or []
        company = intel.company
        role = role_target or "the role"

        # Tech stack matches
        co_stack = {self._norm(t) for t in (intel.tech_stack.value or [])}
        cand_stack = [s for s in candidate_skills if self._norm(s) in co_stack]

        # Resume bullet hooks
        resume_hooks: List[str] = []
        if cand_stack:
            resume_hooks.append(
                f"Lead bullet with quantified impact in {', '.join(cand_stack[:3])}"
                f" — direct overlap with {company}'s stack."
            )
        if intel.company_stage.value:
            stage = str(intel.company_stage.value).replace("_", " ")
            resume_hooks.append(
                f"Highlight scale-appropriate work — {company} is {stage};"
                " emphasize ownership over polish."
            )
        if intel.headcount.value:
            resume_hooks.append(
                f"Frame leadership / cross-functional bullets to match "
                f"~{intel.headcount.value}-person team dynamics."
            )
        if not resume_hooks:
            resume_hooks.append(
                "Quantify recent wins with metric + outcome + scope."
            )

        # Cover letter hooks
        cover_hooks: List[str] = []
        leaders = intel.leadership.value or []
        if leaders:
            ceo = next((p for p in leaders if "ceo" in self._norm(p.get("title", ""))),
                       leaders[0] if leaders else None)
            if ceo:
                cover_hooks.append(
                    f"Reference {ceo.get('name')}'s public direction for "
                    f"{company}; tie your motivation to that thesis."
                )
        recent_news = intel.recent_news.value or []
        if recent_news:
            top = recent_news[0]
            cover_hooks.append(
                f"Open with the recent {company} news: \"{top.get('title')}\""
                f" — connect to your relevant experience."
            )
        if intel.values.value:
            vals = ", ".join(str(v) for v in intel.values.value[:3])
            cover_hooks.append(
                f"Mirror {company}'s stated values ({vals}) with one"
                " concrete example from your work."
            )
        if not cover_hooks:
            cover_hooks.append(
                f"Lead with one sentence on why {company} (specifically) and"
                f" why {role} (specifically) — avoid generic praise."
            )

        # Interview questions (intel-driven)
        questions: List[str] = []
        if intel.last_round.value:
            questions.append(
                f"How has the {intel.last_round.value} round shifted "
                f"team-level priorities for the next 6 months?"
            )
        if intel.tech_stack.value:
            stack_sample = ", ".join(str(t) for t in intel.tech_stack.value[:3])
            questions.append(
                f"You use {stack_sample} — where in the stack are you"
                " feeling the most architectural pressure right now?"
            )
        if intel.competitors.value:
            comp = intel.competitors.value[0]
            questions.append(
                f"How do you think about your moat versus {comp}?"
            )
        if intel.glassdoor_themes.value:
            theme = next(
                (t for t in intel.glassdoor_themes.value
                 if t and t.lower() in {"intense workload", "fast-paced",
                                        "burnout", "long hours"}),
                None,
            )
            if theme:
                questions.append(
                    f"Glassdoor reviews mention \"{theme}\" — what's the"
                    " team doing this quarter to address that?"
                )
        if intel.recent_news.value:
            questions.append(
                f"What does the recent \"{intel.recent_news.value[0].get('title')}\""
                f" change about hiring priorities for {role}?"
            )
        if intel.research_papers.value:
            paper = intel.research_papers.value[0]
            if isinstance(paper, dict) and paper.get("title"):
                questions.append(
                    f"I read your team's paper \"{paper['title']}\" on arXiv"
                    f" — how does that research feed into the"
                    f" product roadmap, and where can {role} contribute?"
                )
        if intel.leadership.value:
            questions.append(
                "Which leader's portfolio would this role most directly"
                " contribute to over the first two quarters?"
            )
        if not questions:
            questions.append(
                f"What does success in {role} look like at the 90-day mark?"
            )
        # Cap at 15
        questions = questions[:15]

        # Talking points
        talking_points: List[str] = []
        for leader in leaders[:3]:
            name = leader.get("name")
            title = leader.get("title")
            if name and title:
                talking_points.append(
                    f"Reference {name} ({title}) by name when relevant —"
                    " shows research."
                )
        if intel.values.value:
            for v in intel.values.value[:3]:
                talking_points.append(
                    f"Bring a concrete story illustrating \"{v}\"."
                )
        if intel.research_papers.value:
            for paper in intel.research_papers.value[:2]:
                if not isinstance(paper, dict):
                    continue
                title = paper.get("title")
                if not title:
                    continue
                talking_points.append(
                    f"Reference the team's paper \"{title}\" — shows you"
                    " engaged with their published research."
                )

        # Differentiation angles
        diff_angles: List[str] = []
        if cand_stack:
            diff_angles.append(
                f"Stack overlap on {', '.join(cand_stack[:3])} — most"
                " applicants will not have shipped production work in"
                " all of these."
            )
        if intel.company_stage.value:
            diff_angles.append(
                f"Bring stage-appropriate stories — {intel.company_stage.value}"
                " requires owners, not specialists."
            )
        if not diff_angles:
            diff_angles.append(
                "Lead with quantified outcomes and the operating decisions"
                " behind them (most candidates lead with activities)."
            )
        if intel.research_papers.value:
            diff_angles.append(
                "Engage substantively with the team's published research"
                " — most applicants will not have read their arXiv work."
            )

        # Red flags
        red_flags: List[str] = []
        if intel.glassdoor_rating.value is not None and \
                isinstance(intel.glassdoor_rating.value, (int, float)) and \
                intel.glassdoor_rating.value < 3.5:
            red_flags.append(
                f"Glassdoor rating {intel.glassdoor_rating.value} — probe"
                " retention and manager quality during interviews."
            )
        for theme in (intel.glassdoor_themes.value or []):
            if isinstance(theme, str) and theme.lower() in {
                "burnout", "long hours", "intense workload",
            }:
                red_flags.append(
                    f"Repeated review theme: \"{theme}\". Validate work-style"
                    " expectations explicitly before signing."
                )
        # Misalignment with candidate values
        norm_co_values = {self._norm(v) for v in (intel.values.value or [])}
        norm_cand_values = {self._norm(v) for v in candidate_values}
        missing = sorted(norm_cand_values - norm_co_values)
        if missing:
            red_flags.append(
                "Your stated values not visible in company signals: "
                + ", ".join(missing[:3])
            )

        return ApplicationKit(
            resume_bullet_hooks=resume_hooks,
            cover_letter_hooks=cover_hooks,
            interview_questions=questions,
            talking_points=talking_points,
            tech_stack_matches=cand_stack,
            differentiation_angles=diff_angles,
            red_flags=red_flags,
        )
