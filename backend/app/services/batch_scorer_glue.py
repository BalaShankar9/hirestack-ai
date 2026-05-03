"""B0.scorer.glue — compose profile + AI + parser into a Scorer.

This module is the thin glue layer between:
  - the pure-fn core (``batch_scorer_core``: prompt + parse), and
  - the production AI router (``ai_engine.client.AIClient``) + the
    Supabase profile fetch.

It exposes ONE public function:

    make_llm_scorer(*, profile_loader, ai_client, jd_loader) -> Scorer

The result is a ``Scorer`` (Awaitable[ScoringResult]) that the route
can drop straight into ``score_plan(...)``.

Why a factory and not a class:
- The route already injects ``Scorer`` via ``get_scorer()`` Depends.
  A factory keeps that surface a plain callable so production-vs-stub
  swaps are a one-line override.
- The three collaborators (profile_loader, ai_client, jd_loader) are
  Protocol-typed so tests never import the real Supabase or AI router
  modules — every test in this file uses simple AsyncMock-style
  fakes.

Resilience contract (every failure → ScoringResult, never an exception):
- profile_loader raises → ScoringResult(error="profile_load_error:<Exc>")
  but ONLY for the first entry; subsequent entries reuse the failure
  cache so we don't hammer the DB.
- jd_loader raises → ScoringResult(error="jd_fetch_error:<Exc>")
- jd_loader returns empty/blank → ScoringResult(error="jd_empty")
- ai_client.complete_json raises → ScoringResult(error="ai_error:<Exc>")
- ai_client returns junk → parse_score_response yields error="parse_error"

The worker layer (``batch_scorer_worker``) wraps ``Scorer`` calls in
its own try/except as a defence-in-depth net (yields "scorer_bug:*"),
but in normal operation we should never hit that net — every error
class is converted to a typed ScoringResult here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Mapping, Optional, Protocol

from app.services.batch_evaluator import BatchEntry, ScoringResult
from app.services.batch_scorer_core import (
    build_profile_text,
    build_score_prompt,
    parse_score_response,
)

logger = logging.getLogger(__name__)


# ── Protocols (typing only; no runtime coupling) ────────────────────


class ProfileLoader(Protocol):
    """Loads the user's primary profile dict (or None if missing)."""

    async def __call__(self, user_id: str) -> Optional[Mapping[str, Any]]: ...


class JDLoader(Protocol):
    """Loads JD plaintext for a given BatchEntry (raises or returns str)."""

    async def __call__(self, entry: BatchEntry) -> str: ...


class AIJSONClient(Protocol):
    """Minimal AI router surface we depend on."""

    async def complete_json(
        self,
        *,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> Any: ...


# ── factory ─────────────────────────────────────────────────────────

Scorer = Callable[[BatchEntry], Awaitable[ScoringResult]]


def make_llm_scorer(
    *,
    user_id: str,
    profile_loader: ProfileLoader,
    jd_loader: JDLoader,
    ai_client: AIJSONClient,
) -> Scorer:
    """Build a ``Scorer`` callable bound to one user.

    The returned scorer is safe to fan out via ``score_plan`` — it
    loads the profile lazily on the first call, then reuses the
    flattened text for every subsequent entry in the batch.

    The profile cache is per-Scorer-instance (per-batch-call) so
    that mid-batch profile edits don't cause inconsistent scoring
    within a single batch.
    """

    # Per-batch profile cache.  ``_loaded`` distinguishes "not yet
    # loaded" from "loaded → None / empty".  ``_load_error`` carries
    # any exception text so we surface it on every entry rather than
    # silently scoring with no profile.  The lock guards against
    # concurrent fan-out (score_plan with concurrency>1) all racing
    # to load the profile simultaneously — only the first racer
    # actually hits the loader; the others await and reuse.
    _loaded = False
    _profile_text: str = ""
    _load_error: Optional[str] = None
    _lock = asyncio.Lock()

    async def _ensure_profile() -> tuple[str, Optional[str]]:
        nonlocal _loaded, _profile_text, _load_error
        if _loaded:
            return _profile_text, _load_error
        async with _lock:
            # Re-check under lock — another racer may have completed
            # the load while we were waiting.
            if _loaded:
                return _profile_text, _load_error
            try:
                raw = await profile_loader(user_id)
                _profile_text = build_profile_text(raw)
            except Exception as exc:  # noqa: BLE001 — converted to typed err
                _load_error = f"profile_load_error:{type(exc).__name__}"
                logger.warning("batch_scorer profile load failed: %s", exc)
            _loaded = True
            return _profile_text, _load_error

    async def _scorer(entry: BatchEntry) -> ScoringResult:
        profile_text, load_err = await _ensure_profile()
        if load_err is not None:
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=None,
                error=load_err,
            )

        # Fetch JD plaintext for THIS entry.
        try:
            jd_text = await jd_loader(entry)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "batch_scorer jd fetch failed url=%s err=%s",
                entry.canonical_url,
                exc,
            )
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=None,
                error=f"jd_fetch_error:{type(exc).__name__}",
            )

        if not jd_text or not jd_text.strip():
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=None,
                error="jd_empty",
            )

        # Build prompt + call AI.
        prompt_block = build_score_prompt(
            profile_text=profile_text,
            jd_text=jd_text,
            canonical_url=entry.canonical_url,
        )
        try:
            response = await ai_client.complete_json(**prompt_block)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "batch_scorer ai call failed url=%s err=%s",
                entry.canonical_url,
                exc,
            )
            return ScoringResult(
                canonical_url=entry.canonical_url,
                fit_score=None,
                error=f"ai_error:{type(exc).__name__}",
            )

        return parse_score_response(response, entry)

    return _scorer


__all__ = [
    "ProfileLoader",
    "JDLoader",
    "AIJSONClient",
    "Scorer",
    "make_llm_scorer",
]
