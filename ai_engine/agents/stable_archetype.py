"""F2 — stable_archetype classifier.

Maps a job description to ONE of 8 fixed archetype labels. Deterministic,
pure-function, no LLM, no I/O. The labels are stable across JDs so
analytics, missions, and cadence customization can group / filter by
archetype reliably (unlike ATLAS's dynamic per-JD archetypes which are
free-text and not comparable across postings).

The 8 labels (chosen for career-ops segmentation, NOT seniority):

  big_tech_ic           Big-Tech IC at FAANG/MAANG-tier scale companies
  startup_founder_adj   Founder-adjacent / early startup builder
  enterprise_saas       Enterprise SaaS product/platform engineer
  regulated_finance     Banks, insurance, payments under regulator
  public_sector         Government, defense, healthcare-public
  research_lab          Industrial / academic research lab
  agency_consulting     Agency, consultancy, professional-services
  hyper_growth_scaleup  Series-B-to-IPO scaleup, "rocketship"
  unknown               Fallback when no archetype scores above threshold

The classifier is keyword-weighted with a small whitelist of company-name
hints. Each archetype contributes a numeric score; the highest score wins
if it exceeds MIN_SCORE_THRESHOLD, otherwise the result is 'unknown'.

A jd_hash (SHA-256, first 16 hex chars) is exposed so callers can cache
the classification next to other JD-derived artifacts. The pure function
itself does NOT cache; callers manage TTL and storage.

DESIGN NOTE: this is intentionally ALL deterministic. An LLM upgrade
path exists (mirror the ATLAS pattern: try heuristic → fall back to LLM
for low-confidence) but ships behind a feature flag in a later slice.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal, Mapping, Optional

# ── Types ─────────────────────────────────────────────────────────────

ArchetypeLabel = Literal[
    "big_tech_ic",
    "startup_founder_adj",
    "enterprise_saas",
    "regulated_finance",
    "public_sector",
    "research_lab",
    "agency_consulting",
    "hyper_growth_scaleup",
    "unknown",
]

ALL_LABELS: tuple[ArchetypeLabel, ...] = (
    "big_tech_ic",
    "startup_founder_adj",
    "enterprise_saas",
    "regulated_finance",
    "public_sector",
    "research_lab",
    "agency_consulting",
    "hyper_growth_scaleup",
)

# Minimum aggregate score for a non-unknown classification.  Tuned so a
# JD must hit at least two distinct keyword cues (each typically worth 1.0)
# before we commit to a label.  Empirically separates "real signal" from
# "one stray buzzword".
MIN_SCORE_THRESHOLD = 2.0

# Margin required between top-1 and top-2 to declare a winner. If the
# margin is too small the result is 'unknown' — caller can choose to
# upgrade to an LLM call later.
MIN_MARGIN = 0.5


@dataclass(frozen=True)
class StableArchetype:
    label: ArchetypeLabel
    confidence: float          # 0.0-1.0 normalized
    raw_score: float           # raw weighted-sum before normalization
    jd_hash: str               # 16-hex SHA-256 prefix of the JD slice
    runner_up: Optional[ArchetypeLabel] = None
    scores: Mapping[ArchetypeLabel, float] = field(default_factory=dict)


# ── Keyword tables ────────────────────────────────────────────────────
#
# Each archetype has:
#   * a set of "strong" tokens worth STRONG_WEIGHT
#   * a set of "weak"   tokens worth WEAK_WEIGHT
# Tokens are matched as whole-word, case-insensitive substrings.
# Weights are intentionally small ints/floats so the threshold logic
# stays tractable.

STRONG_WEIGHT = 1.5
WEAK_WEIGHT = 0.6

# Case-insensitive whole-word match (allows hyphens within words).
_TOKEN_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _token_re(token: str) -> re.Pattern[str]:
    pat = _TOKEN_RE_CACHE.get(token)
    if pat is None:
        # Match as a "word" with simple boundaries that allow letters,
        # digits, underscore, hyphen.  We use lookarounds to avoid
        # \b's quirks around hyphens.
        escaped = re.escape(token)
        pat = re.compile(
            rf"(?<![A-Za-z0-9_\-]){escaped}(?![A-Za-z0-9_\-])",
            re.IGNORECASE,
        )
        _TOKEN_RE_CACHE[token] = pat
    return pat


_KEYWORDS: dict[ArchetypeLabel, dict[str, list[str]]] = {
    "big_tech_ic": {
        "strong": [
            "google", "alphabet", "meta", "facebook", "amazon", "microsoft",
            "apple", "netflix", "nvidia",
            "faang", "maang", "big tech",
            "billions of users", "planet-scale", "global scale",
        ],
        "weak": [
            "distributed systems", "high scale", "rfc", "design doc",
            "principal engineer", "staff engineer", "tech lead manager",
            "performance review", "promo packet",
        ],
    },
    "startup_founder_adj": {
        "strong": [
            "founding engineer", "founding member", "founding team",
            "early-stage", "early stage startup", "pre-seed", "seed-stage",
            "0 to 1", "0-to-1", "zero to one",
            "wear many hats", "many hats",
        ],
        "weak": [
            "scrappy", "ambiguous", "ambiguity", "ship fast",
            "no playbook", "founder-led", "fast-paced startup",
            "small team", "founding",
        ],
    },
    "enterprise_saas": {
        "strong": [
            "enterprise saas", "b2b saas", "multi-tenant", "multitenant",
            "enterprise customers", "fortune 500 customers",
            "single sign-on", "scim provisioning", "soc 2 type ii",
        ],
        "weak": [
            "saas platform", "tenant isolation", "rbac", "audit log",
            "enterprise readiness", "soc2", "iso 27001",
            "platform team",
        ],
    },
    "regulated_finance": {
        "strong": [
            "investment bank", "retail bank", "broker-dealer",
            "finra", "sec-registered", "pci dss", "pci-dss",
            "kyc", "aml", "anti-money-laundering",
            "basel iii", "dodd-frank", "mifid",
        ],
        "weak": [
            "compliance", "regulatory", "regulator", "audit",
            "trading systems", "risk management", "underwriting",
            "insurance", "claims", "actuarial", "payments",
        ],
    },
    "public_sector": {
        "strong": [
            "fedramp", "us citizen", "u.s. citizen",
            "security clearance", "top secret", "ts/sci", "secret clearance",
            "federal government", "department of defense", "dod",
            "nhs", "ministry of", "public health",
            "gs-13", "gs-14", "gs-15",
        ],
        "weak": [
            "government", "agency", "veteran", "public-sector",
            "civic", "citizen-facing", "fips", "nist 800",
        ],
    },
    "research_lab": {
        "strong": [
            "research scientist", "research engineer",
            "publish at", "publications at", "first-author publication",
            "phd preferred", "phd required", "ph.d.",
            "neurips", "icml", "iclr", "cvpr", "acl ", "emnlp",
            "deepmind", "openai research", "fair ", "google brain",
            "microsoft research",
        ],
        "weak": [
            "novel research", "state-of-the-art", "sota",
            "research direction", "publication record",
            "advance the state", "ablation",
        ],
    },
    "agency_consulting": {
        "strong": [
            "consultancy", "consulting firm",
            "client engagements", "client-facing", "billable hours",
            "utilization rate", "utilisation rate",
            "deloitte", "accenture", "mckinsey", "bain", "bcg",
            "thoughtworks",
        ],
        "weak": [
            "agency", "consultant", "engagement", "client work",
            "delivery team", "project-based", "statement of work",
            "sow ",
        ],
    },
    "hyper_growth_scaleup": {
        "strong": [
            "series b", "series c", "series d", "series e",
            "rocketship", "hypergrowth", "hyper-growth", "hyper growth",
            "pre-ipo", "rapidly scaling", "scaling our team",
            "100% yoy", "doubling annually", "2x year over year",
        ],
        "weak": [
            "scale-up", "scaleup", "growing fast",
            "category leader", "next unicorn", "unicorn",
            "blitzscaling",
        ],
    },
}


# ── Internals ─────────────────────────────────────────────────────────


def _normalize(jd: str) -> str:
    """Collapse whitespace; everything else stays — keyword regex is
    case-insensitive and handles its own boundaries."""
    if not jd:
        return ""
    # Collapse runs of whitespace to a single space so multi-word
    # tokens like "founding engineer" match across newlines.
    return re.sub(r"\s+", " ", jd)


def _score_label(jd_text: str, tokens: dict[str, list[str]]) -> float:
    """Sum keyword weights for a single archetype.

    Each unique token contributes AT MOST ONCE (no count bonus), so a
    single repeated buzzword can't dominate.
    """
    score = 0.0
    for token in tokens.get("strong", []):
        if _token_re(token).search(jd_text):
            score += STRONG_WEIGHT
    for token in tokens.get("weak", []):
        if _token_re(token).search(jd_text):
            score += WEAK_WEIGHT
    return score


def _hash_jd(jd: str) -> str:
    return hashlib.sha256(
        (jd or "")[:6000].encode("utf-8", errors="ignore")
    ).hexdigest()[:16]


# ── Public API ────────────────────────────────────────────────────────


def jd_hash(job_description: str) -> str:
    """Stable 16-hex digest of the leading 6000 chars of a JD.

    Mirrors the ATLAS cache-key digest length so the same hash can serve
    as a join key across both subsystems.
    """
    return _hash_jd(job_description)


def classify(job_description: str) -> StableArchetype:
    """Classify a JD into one of 8 fixed labels (or 'unknown').

    Pure function: same input → same output. No I/O, no caching, no LLM.
    Returns a StableArchetype with the winning label, confidence, and
    the full per-label score map for callers that want to inspect ties.
    """
    digest = _hash_jd(job_description)
    if not job_description or not job_description.strip():
        return StableArchetype(
            label="unknown",
            confidence=0.0,
            raw_score=0.0,
            jd_hash=digest,
            runner_up=None,
            scores={lbl: 0.0 for lbl in ALL_LABELS},
        )

    text = _normalize(job_description)
    scores: dict[ArchetypeLabel, float] = {
        lbl: round(_score_label(text, _KEYWORDS[lbl]), 3) for lbl in ALL_LABELS
    }

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_label, top_score = ranked[0]
    runner_label, runner_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

    if top_score < MIN_SCORE_THRESHOLD or (top_score - runner_score) < MIN_MARGIN:
        return StableArchetype(
            label="unknown",
            confidence=0.0,
            raw_score=top_score,
            jd_hash=digest,
            runner_up=top_label,  # surface what *almost* won
            scores=scores,
        )

    # Confidence: how decisively top beat runner-up, capped at 1.0.
    # margin/(top + epsilon) puts a clean win at ~0.6+; a runaway at 1.0.
    margin = top_score - runner_score
    confidence = min(1.0, round(margin / max(top_score, 0.001), 3))

    return StableArchetype(
        label=top_label,
        confidence=confidence,
        raw_score=top_score,
        jd_hash=digest,
        runner_up=runner_label,
        scores=scores,
    )
