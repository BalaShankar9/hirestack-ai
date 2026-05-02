"""
Posting legitimacy — combines liveness classification with URL/ATS
heuristics to produce a four-tier legitimacy verdict for a job posting.

Pure composer over:
  - liveness_classifier.classify_liveness  (page-level signals)
  - url_canonicalizer.canonicalize_url     (dedup / repost detection)
  - url_canonicalizer.extract_ats_key      (provenance signal)

Designed to be HTTP-agnostic: caller fetches the page (via httpx,
Playwright, or a cached snapshot) and passes the materials in.
This makes the service trivially testable and lets the public
`/ghost-check` endpoint cache aggressively.

Verdict tiers (UI-facing):
    LEGITIMATE — live posting on a known ATS with strong signals
    CAUTION    — live but ambiguous (long-running, no ATS, thin page)
    GHOST      — strong removed/expired/unreachable signals
    UNKNOWN    — insufficient evidence to call

The verdict is intentionally conservative on accusatory tier
assignments (we never CALL a posting fraudulent — we present
signals; user decides). See HARD-RULE #3 in MASTER_INTEGRATION_PLAN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from app.services.liveness_classifier import (
    Liveness,
    LivenessResult,
    classify_liveness,
)
from app.services.url_canonicalizer import canonicalize_url, extract_ats_key


class LegitimacyTier(str, Enum):
    LEGITIMATE = "legitimate"
    CAUTION = "caution"
    GHOST = "ghost"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PostingLegitimacy:
    """User-facing legitimacy report for a single job posting URL.

    Attributes:
        tier:           Final verdict (one of LegitimacyTier).
        confidence:     0.0–1.0; aggregated from liveness + heuristics.
        url_canonical:  Normalized URL (for caching / dedup).
        ats_provider:   Detected ATS provider, or None if not on a
                        known ATS (one signal of caution).
        ats_company:    Company slug as it appears in the ATS URL.
        ats_job_id:     Job ID as it appears in the ATS URL.
        liveness:       Underlying LivenessResult.
        signals:        Ordered, transparent list of every signal
                        considered; safe for UI display.
        reasoning:      Short list of human-readable bullet points;
                        never accusatory (HARD-RULE #3).
        evaluated_at:   When this verdict was computed.
    """

    tier: LegitimacyTier
    confidence: float
    url_canonical: str
    ats_provider: str | None
    ats_company: str | None
    ats_job_id: str | None
    liveness: LivenessResult
    signals: tuple[str, ...] = field(default_factory=tuple)
    reasoning: tuple[str, ...] = field(default_factory=tuple)
    evaluated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "tier": self.tier.value,
            "confidence": self.confidence,
            "url_canonical": self.url_canonical,
            "ats_provider": self.ats_provider,
            "ats_company": self.ats_company,
            "ats_job_id": self.ats_job_id,
            "liveness": self.liveness.to_dict(),
            "signals": list(self.signals),
            "reasoning": list(self.reasoning),
            "evaluated_at": self.evaluated_at,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def evaluate_posting_legitimacy(
    *,
    url: str,
    status: int = 0,
    final_url: str = "",
    body_text: str = "",
    apply_controls: Sequence[str] = (),
    repost_count: int = 0,
    age_days: int | None = None,
) -> PostingLegitimacy:
    """Combine liveness + URL/ATS heuristics into a legitimacy verdict.

    Args:
        url:            The original URL the user submitted.
        status, final_url, body_text, apply_controls:
                        Forwarded to classify_liveness; pre-fetched by
                        caller (HTTP or Playwright).
        repost_count:   How many times this canonical URL has been seen
                        in our scan history. >= 3 is a soft ghost signal
                        (career-ops's "frequently reposted" heuristic).
        age_days:       How long ago this URL was first seen. > 90 days
                        with status==active is a "perpetual posting"
                        signal — soft caution.

    Returns:
        PostingLegitimacy — never raises.
    """
    canonical = canonicalize_url(url) if url else ""
    ats_key = extract_ats_key(canonical) if canonical else None
    ats_provider, ats_company, ats_job_id = (
        ats_key if ats_key is not None else (None, None, None)
    )

    liveness = classify_liveness(
        status=status,
        final_url=final_url,
        body_text=body_text,
        apply_controls=apply_controls,
    )

    signals: list[str] = list(liveness.signals)
    reasoning: list[str] = []

    # ── Compose tier ─────────────────────────────────────────────────
    # Strong removed signals → GHOST regardless of ATS provenance.
    if liveness.liveness is Liveness.REMOVED:
        tier = LegitimacyTier.GHOST
        confidence = liveness.confidence
        reasoning.append(f"Posting page indicates removal: {liveness.reason}")
        if ats_provider:
            signals.append(f"ats_provider:{ats_provider}")
            reasoning.append(
                f"Posted on {ats_provider} (known ATS) — removal signal is high-confidence."
            )

    # Live + on a known ATS → LEGITIMATE.
    elif liveness.liveness is Liveness.LIVE and ats_provider is not None:
        tier = LegitimacyTier.LEGITIMATE
        confidence = min(1.0, liveness.confidence + 0.05)
        signals.append(f"ats_provider:{ats_provider}")
        reasoning.append(
            f"Live posting on {ats_provider} — visible apply control + recognized ATS."
        )

    # Live but no recognized ATS → CAUTION (could be self-hosted or scam).
    elif liveness.liveness is Liveness.LIVE:
        tier = LegitimacyTier.CAUTION
        confidence = max(0.4, liveness.confidence - 0.2)
        signals.append("ats_provider:unrecognized")
        reasoning.append(
            "Live posting but not on a recognized ATS (Greenhouse, Lever, "
            "Ashby, Workday, Workable, SmartRecruiters). Verify the company "
            "and posting independently before applying."
        )

    # UNKNOWN liveness — fold in repost/age heuristics if available.
    else:
        tier = LegitimacyTier.UNKNOWN
        confidence = liveness.confidence
        reasoning.append(
            "Insufficient on-page signals to classify. The posting may be "
            "behind a login wall, server-rendered after auth, or a JavaScript "
            "shell that didn't load."
        )
        if ats_provider:
            signals.append(f"ats_provider:{ats_provider}")
            reasoning.append(
                f"URL matches a known ATS pattern ({ats_provider}); the page "
                "structure suggests it exists but doesn't expose an apply control "
                "to anonymous fetch."
            )

    # ── Soft signals layered on top of the verdict ────────────────────
    # Repost frequency: career-ops treats >=3 as "frequently reposted".
    if repost_count >= 3:
        signals.append(f"repost_count:{repost_count}")
        reasoning.append(
            f"Seen {repost_count} times in our scan history — frequently "
            "reposted roles can indicate hiring difficulties, repeated "
            "ghosting, or evergreen pipeline-building."
        )
        # Soft penalty on confidence if we already called LEGITIMATE.
        if tier is LegitimacyTier.LEGITIMATE:
            confidence = max(0.5, confidence - 0.1)
            tier = LegitimacyTier.CAUTION
            reasoning.append("Downgraded LEGITIMATE → CAUTION due to repost frequency.")

    # Age: > 90 days old + still active is a "perpetual posting" smell.
    if age_days is not None and age_days > 90 and tier in (LegitimacyTier.LEGITIMATE, LegitimacyTier.CAUTION):
        signals.append(f"age_days:{age_days}")
        reasoning.append(
            f"This posting has been live for {age_days} days. Roles that "
            "remain open beyond ~90 days without filling can indicate "
            "evergreen pipeline-building or a stalled requisition."
        )
        if tier is LegitimacyTier.LEGITIMATE:
            confidence = max(0.5, confidence - 0.1)
            tier = LegitimacyTier.CAUTION
            reasoning.append("Downgraded LEGITIMATE → CAUTION due to posting age.")

    return PostingLegitimacy(
        tier=tier,
        confidence=round(confidence, 2),
        url_canonical=canonical,
        ats_provider=ats_provider,
        ats_company=ats_company,
        ats_job_id=ats_job_id,
        liveness=liveness,
        signals=tuple(signals),
        reasoning=tuple(reasoning),
        evaluated_at=_now_iso(),
    )


__all__ = [
    "LegitimacyTier",
    "PostingLegitimacy",
    "evaluate_posting_legitimacy",
]
