"""B0.scorer core — pure-fn prompt + parser for batch URL scoring.

The end-to-end batch scoring pipeline is:

    URL → (B0.fetcher: fetch+strip JD HTML)
        → JD plaintext + user profile
        → (THIS MODULE: build_score_prompt → AI call → parse_score_response)
        → ScoringResult

This module owns the pure-fn pieces:
- ``build_profile_text``: collapse a profile dict into a stable
  prompt-friendly block.
- ``build_score_prompt``: assemble the full system + user prompt.
- ``parse_score_response``: validate & coerce the JSON the model
  returns into a ``ScoringResult``.

The actual ``ai_client.complete_json`` call is a 10-line glue layer
that lives in the route's Scorer factory (separate slice) so this
module stays AI-router-free and trivially testable.

Hard rules:
- ``match_score`` from the model is 0-100; we rescale to 0.0-5.0
  before storing in ``ScoringResult.fit_score`` to match the rest
  of the batch_evaluator surface.
- Out-of-range scores are clamped, not errored — the model
  occasionally returns 105 or -5 and we shouldn't 500 the user.
- A response missing required keys yields ScoringResult with
  ``error="parse_error"`` so rank_batch can bucket it as failed.
- We ALWAYS pin canonical_url to the entry's value, never to
  whatever the model echoed back.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from app.services.batch_evaluator import BatchEntry, ScoringResult


# ── tunables ─────────────────────────────────────────────────────────

# Cap how much JD text we send to the model.  Most JD pages are
# < 4 KB after HTML strip; 8000 chars is ~2k tokens, leaving plenty
# of budget for the profile + system prompt + response.
MAX_JD_CHARS = 8000

# Same cap for profile-side text.  Keeps prompt cost predictable
# regardless of how many skills/jobs a user has on file.
MAX_PROFILE_CHARS = 4000

# Model returns 0-100; we use 0-5.  scaled = match_score / 20.
SCORE_SCALE = 20.0
SCORE_MIN = 0.0
SCORE_MAX = 5.0


# ── profile flattening ───────────────────────────────────────────────


def build_profile_text(profile: Optional[Mapping[str, Any]]) -> str:
    """Collapse a profile dict into a deterministic prompt block.

    Order is fixed so caching works (same profile → same string →
    same prompt → cache hit on the AI router side).  Missing fields
    render as empty strings rather than the literal "None" so the
    model doesn't see noise.
    """
    if profile is None:
        return "(no profile on file)"

    title = str(profile.get("title") or "").strip()
    summary = str(profile.get("summary") or "").strip()

    skills_raw = profile.get("skills") or []
    skill_names: list[str] = []
    if isinstance(skills_raw, list):
        for s in skills_raw:
            if isinstance(s, Mapping):
                name = str(s.get("name") or "").strip()
            else:
                name = str(s or "").strip()
            if name:
                skill_names.append(name)

    parts: list[str] = []
    if title:
        parts.append(f"Title: {title}")
    if skill_names:
        parts.append(f"Skills: {', '.join(skill_names)}")
    if summary:
        parts.append(f"Summary: {summary}")

    text = "\n".join(parts) if parts else "(profile is empty)"
    if len(text) > MAX_PROFILE_CHARS:
        text = text[:MAX_PROFILE_CHARS].rstrip() + "…"
    return text


# ── prompt builder ───────────────────────────────────────────────────

SCORE_SYSTEM_PROMPT = (
    "You are a job-fit scoring expert. Score how well the candidate's "
    "profile matches the job posting on a 0-100 scale. Be honest and "
    "specific. Return ONLY valid JSON matching the schema in the user "
    "message — no prose, no code fences, no commentary."
)


def build_score_prompt(
    *,
    profile_text: str,
    jd_text: str,
    canonical_url: str,
) -> dict[str, Any]:
    """Assemble the full prompt block for ``ai_client.complete_json``.

    Returns a dict with keys ``system``, ``prompt``, and ``max_tokens``
    so callers can splat it directly: ``await client.complete_json(**block)``.

    The schema we ask for is intentionally narrow:
        match_score: 0-100 int
        match_reasons: list[str]   (max 5)
        missing_skills: list[str]  (max 5)
        title: str (best-guess job title from JD)
        company: str (best-guess company name from JD)
    """
    truncated_jd = jd_text[:MAX_JD_CHARS]
    if len(jd_text) > MAX_JD_CHARS:
        truncated_jd = truncated_jd.rstrip() + "…"

    user_prompt = (
        "Score this candidate against this job posting.\n\n"
        "CANDIDATE PROFILE:\n"
        f"{profile_text}\n\n"
        f"JOB POSTING (source: {canonical_url}):\n"
        f"{truncated_jd}\n\n"
        "Return ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "match_score": <integer 0-100>,\n'
        '  "match_reasons": [<up to 5 short strings>],\n'
        '  "missing_skills": [<up to 5 short strings>],\n'
        '  "title": "<best-guess job title>",\n'
        '  "company": "<best-guess company name>"\n'
        "}"
    )

    return {
        "system": SCORE_SYSTEM_PROMPT,
        "prompt": user_prompt,
        "max_tokens": 512,
    }


# ── response parsing ─────────────────────────────────────────────────


def _coerce_score(raw: Any) -> Optional[float]:
    """Coerce raw model output to a clamped float in [SCORE_MIN, SCORE_MAX].

    Returns ``None`` if the value can't be coerced at all.  Out-of-
    range numbers are clamped, not rejected, because models occasionally
    overshoot and a 105 from the model should still surface as 5.0.
    """
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    scaled = v / SCORE_SCALE
    if scaled < SCORE_MIN:
        return SCORE_MIN
    if scaled > SCORE_MAX:
        return SCORE_MAX
    return scaled


def _coerce_str(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    return s if s else None


def parse_score_response(
    response: Any,
    entry: BatchEntry,
) -> ScoringResult:
    """Convert the model's JSON response into a ``ScoringResult``.

    * Non-dict response → error="parse_error".
    * Missing or non-numeric ``match_score`` → error="parse_error".
    * Out-of-range ``match_score`` → clamped to [0, 5] (no error).
    * canonical_url is ALWAYS pinned to ``entry.canonical_url``;
      anything the model echoed is ignored.
    * ``title`` and ``company`` are optional convenience fields the UI
      may render alongside the score.
    """
    if not isinstance(response, Mapping):
        return ScoringResult(
            canonical_url=entry.canonical_url,
            fit_score=None,
            error="parse_error",
        )

    fit = _coerce_score(response.get("match_score"))
    if fit is None:
        return ScoringResult(
            canonical_url=entry.canonical_url,
            fit_score=None,
            error="parse_error",
        )

    return ScoringResult(
        canonical_url=entry.canonical_url,
        fit_score=fit,
        error=None,
        title=_coerce_str(response.get("title")),
        company=_coerce_str(response.get("company")),
    )


__all__ = [
    "MAX_JD_CHARS",
    "MAX_PROFILE_CHARS",
    "SCORE_SCALE",
    "SCORE_MIN",
    "SCORE_MAX",
    "SCORE_SYSTEM_PROMPT",
    "build_profile_text",
    "build_score_prompt",
    "parse_score_response",
]
