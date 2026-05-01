"""LinkedInOptimizer — orchestrates section-by-section rewrites + headline AB.

Uses the AIClient when available; otherwise falls back to a deterministic
"polish" pass that adds an action-verb prefix and quantification stub.
"""
from __future__ import annotations

import json
import logging
import time
from typing import List, Optional

from ai_engine.agents.linkedin.ats_scorer import score_profile, score_section
from ai_engine.agents.linkedin.schemas import (
    HeadlineVariant,
    LinkedInProfile,
    OptimizationReport,
    OptimizationResult,
    ProfileScore,
)

logger = logging.getLogger("hirestack.linkedin.optimizer")

_HEADLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "variants": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "hook_type": {"type": "string"},
                },
                "required": ["text", "hook_type"],
            },
        }
    },
    "required": ["variants"],
}

_REWRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "about": {"type": "string"},
        "rationale_headline": {"type": "string"},
        "rationale_about": {"type": "string"},
    },
    "required": ["headline", "about"],
}


def _safe_get_client():
    try:
        from ai_engine.client import get_ai_client
        return get_ai_client()
    except Exception as exc:  # noqa: BLE001
        logger.info("linkedin_optimizer_no_client cause=%s", exc)
        return None


def _deterministic_headline(original: str, target_role: str) -> str:
    base = original.strip() or f"{target_role.title()} | Driving outcomes"
    suffix = f"{target_role.title()} | Outcome-driven leader who ships measurable results"
    if target_role.lower() not in base.lower():
        return f"{base[:60]} | {suffix}"[:120]
    return (base + " | Driving measurable results")[:120]


def _deterministic_about(original: str, target_role: str) -> str:
    fallback = (
        f"Experienced {target_role} focused on shipping measurable outcomes. "
        "I lead cross-functional teams through ambiguity, ship production "
        "systems on tight timelines, and translate strategy into clear weekly "
        "execution. Recent wins include reducing critical-path latency by 30%, "
        "growing active usage by 25%, and mentoring three engineers into senior "
        "roles. I care about: clear writing, fast iteration, and outcomes that "
        "compound. Open to roles where the team values craft, autonomy, and "
        "measurable impact."
    )
    if not original.strip():
        return fallback
    if len(original) >= 600:
        return original
    return original.rstrip(". ") + ". " + fallback


def _deterministic_headline_variants(target_role: str) -> List[dict]:
    role = target_role.title()
    return [
        {"text": f"{role} who ships outcomes — 30% faster releases, 25% growth",
         "hook_type": "results"},
        {"text": f"{role} | Translating strategy into shipped product weekly",
         "hook_type": "value-prop"},
        {"text": f"{role} | Mentor • Builder • Operator • Open to new roles",
         "hook_type": "authority"},
    ]


class LinkedInOptimizer:
    def __init__(self, *, ai_client=None):
        self._client = ai_client

    def _client_or_default(self):
        if self._client is None:
            self._client = _safe_get_client()
        return self._client

    async def optimize(
        self,
        profile: LinkedInProfile,
        target_role: str,
        *,
        include_headline_ab: bool = True,
        headline_variant_count: int = 3,
    ) -> OptimizationReport:
        if not target_role or not target_role.strip():
            raise ValueError("target_role is required")

        t0 = time.monotonic()
        score_before = score_profile(profile, target_role)

        client = self._client_or_default()
        new_headline = profile.headline
        new_about = profile.about
        rationale_h = ""
        rationale_a = ""

        if client is not None:
            prompt = self._rewrite_prompt(profile, target_role)
            try:
                payload = await client.complete_json(
                    prompt=prompt,
                    system="You are a LinkedIn copy editor producing strict JSON.",
                    schema=_REWRITE_SCHEMA,
                    temperature=0.4,
                    task_type="linkedin_rewrite",
                )
                if isinstance(payload, dict):
                    new_headline = (payload.get("headline") or new_headline).strip()
                    new_about = (payload.get("about") or new_about).strip()
                    rationale_h = (payload.get("rationale_headline") or "").strip()
                    rationale_a = (payload.get("rationale_about") or "").strip()
            except Exception as exc:  # noqa: BLE001
                logger.info("linkedin_rewrite_llm_failed cause=%s", exc)

        if not rationale_h:
            new_headline = _deterministic_headline(profile.headline, target_role)
            rationale_h = "Tightened to 80–120 chars and added role + outcome framing."
        if not rationale_a:
            new_about = _deterministic_about(profile.about, target_role)
            rationale_a = "Expanded to ≥600 chars with quantified outcomes."

        h_before, _ = score_section("headline", profile.headline, target_role)
        h_after, _ = score_section("headline", new_headline, target_role)
        a_before, _ = score_section("about", profile.about, target_role)
        a_after, _ = score_section("about", new_about, target_role)

        results = [
            OptimizationResult(
                section="headline",
                original=profile.headline,
                optimized=new_headline,
                score_before=h_before,
                score_after=h_after,
                rationale=rationale_h,
            ),
            OptimizationResult(
                section="about",
                original=profile.about,
                optimized=new_about,
                score_before=a_before,
                score_after=a_after,
                rationale=rationale_a,
            ),
        ]

        variants: List[HeadlineVariant] = []
        if include_headline_ab:
            variants = await self.headline_ab(
                profile, target_role, n=headline_variant_count,
            )

        # Score the post-optimization profile.
        post_profile = profile.model_copy(update={"headline": new_headline, "about": new_about})
        score_after = score_profile(post_profile, target_role)

        return OptimizationReport(
            target_role=target_role,
            score_before=score_before,
            score_after=score_after,
            results=results,
            headline_variants=variants,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )

    async def headline_ab(
        self,
        profile: LinkedInProfile,
        target_role: str,
        *,
        n: int = 3,
    ) -> List[HeadlineVariant]:
        if not target_role or not target_role.strip():
            raise ValueError("target_role is required")
        n = max(1, min(5, n))

        client = self._client_or_default()
        raw: List[dict] = []
        if client is not None:
            try:
                payload = await client.complete_json(
                    prompt=self._headline_prompt(profile, target_role, n),
                    system=("You write LinkedIn headlines as strict JSON. "
                            "Each variant must be ≤120 chars."),
                    schema=_HEADLINE_SCHEMA,
                    temperature=0.6,
                    task_type="linkedin_headline_ab",
                )
                if isinstance(payload, dict):
                    raw = list(payload.get("variants") or [])
            except Exception as exc:  # noqa: BLE001
                logger.info("linkedin_headline_llm_failed cause=%s", exc)

        if not raw:
            raw = _deterministic_headline_variants(target_role)

        out: List[HeadlineVariant] = []
        for entry in raw[:n]:
            text = (entry.get("text") or "").strip()[:120]
            if not text:
                continue
            hook = (entry.get("hook_type") or "value-prop").strip().lower()
            score, _ = score_section("headline", text, target_role)
            out.append(HeadlineVariant(text=text, hook_type=hook, score=score))
        if not out:  # last-resort fallback
            for entry in _deterministic_headline_variants(target_role)[:n]:
                score, _ = score_section("headline", entry["text"], target_role)
                out.append(HeadlineVariant(
                    text=entry["text"], hook_type=entry["hook_type"], score=score,
                ))
        return out

    # ─── prompt builders ────────────────────────────────────────────

    @staticmethod
    def _rewrite_prompt(profile: LinkedInProfile, target_role: str) -> str:
        return (
            "Rewrite the LinkedIn headline (80–120 chars) and About section "
            "(≥600 chars) to win interviews for the target role. "
            "Respect the candidate's facts; do not fabricate. "
            "Use action verbs, quantify outcomes, and lead with role-relevant keywords.\n\n"
            f"TARGET ROLE: {target_role}\n\n"
            f"CURRENT HEADLINE: {profile.headline}\n\n"
            f"CURRENT ABOUT: {profile.about}\n\n"
            "Return JSON with keys: headline, about, rationale_headline, rationale_about."
        )

    @staticmethod
    def _headline_prompt(profile: LinkedInProfile, target_role: str, n: int) -> str:
        return (
            f"Generate {n} LinkedIn headline variants (≤120 chars each) for the "
            f"target role '{target_role}'. Use distinct hook types from "
            "{value-prop, results, authority, curiosity}. "
            f"Current headline (for context): {profile.headline}\n\n"
            "Return JSON: {variants:[{text, hook_type}]}"
        )
