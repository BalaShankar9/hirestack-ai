"""Auto-prep tracked-company discoveries into queued generation jobs.

This slice closes the gap between "watchlist found a promising role" and
"the user already has a prepared workspace with generation running".

Behavior:
* Read the user's enabled tracked companies.
* Pull recent discoveries from ``job_scan_history`` for those slugs.
* Re-score them with the live batch scorer.
* Enrich the top hits with JD text.
* Create application rows with the job title + JD persisted in
  ``confirmed_facts`` so the generation runtime has the inputs it needs.
* Queue a generation job for each prepared application.

The implementation is intentionally conservative for the first production
slice: only the strongest few hits are prepared, and the whole feature is a
best-effort no-op when the live scorer is not enabled.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Awaitable, Callable, Dict, List, Mapping, Optional

import httpx

from app.core.database import TABLES, SupabaseDB, get_db, get_supabase
from app.services.batch_evaluator import BatchEntry, ScoringResult, rank_batch
from app.services.batch_jd_fetcher import JDLoader, make_jd_loader
from app.services.batch_persister import make_batch_id
from app.services.batch_persister_core import build_application_row, make_dedup_key
from app.services.batch_scorer_glue import Scorer, make_llm_scorer
from app.services.batch_scorer_worker import DEFAULT_CONCURRENCY, score_plan
from app.services.url_canonicalizer import extract_ats_key

logger = logging.getLogger(__name__)

_LIVE_FLAG_ENV = "BATCH_SCORER_LIVE"
_LIVE_FETCH_TIMEOUT_S = 12.0
_LIVE_USER_AGENT = "HireStack/1.0 AutoPrep (+https://hirestack.ai)"

AUTO_PREP_DISCOVERY_WINDOW_HOURS = 48
AUTO_PREP_CANDIDATE_LIMIT = 12
AUTO_PREP_DEFAULT_LIMIT = 3
AUTO_PREP_DEFAULT_MIN_FIT_SCORE = 4.0
AUTO_PREP_REQUESTED_MODULES = [
    "benchmark",
    "gaps",
    "learningPlan",
    "cv",
    "coverLetter",
    "scorecard",
]

ScorerFactory = Callable[[str], Scorer]
JDLoaderFactory = Callable[[], JDLoader]
JobCreator = Callable[..., Awaitable[str]]


def _is_live_enabled() -> bool:
    val = os.getenv(_LIVE_FLAG_ENV, "").strip().lower()
    return val in {"1", "true", "yes", "on"}


async def _live_httpx_fetcher(url: str) -> str:
    headers = {
        "User-Agent": _LIVE_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        timeout=_LIVE_FETCH_TIMEOUT_S,
        follow_redirects=True,
        max_redirects=3,
        headers=headers,
    ) as client:
        resp = await client.get(url)
        return resp.text or ""


@lru_cache(maxsize=1)
def _shared_jd_loader() -> JDLoader:
    return make_jd_loader(fetcher=_live_httpx_fetcher)


@lru_cache(maxsize=1)
def _shared_ai_client() -> Any:
    from ai_engine.api import get_ai_client

    return get_ai_client()


@lru_cache(maxsize=1)
def _shared_profile_service() -> Any:
    from app.services.profile import ProfileService

    return ProfileService()


async def _live_profile_loader(user_id: str) -> Optional[Dict[str, Any]]:
    svc = _shared_profile_service()
    return await svc.get_primary_profile(user_id)


def _build_live_scorer(user_id: str) -> Scorer:
    return make_llm_scorer(
        user_id=user_id,
        profile_loader=_live_profile_loader,
        jd_loader=_shared_jd_loader(),
        ai_client=_shared_ai_client(),
    )


async def _default_job_creator(
    *,
    application_id: str,
    user_id: str,
    requested_modules: List[str],
    application_modules: Optional[Dict[str, Any]] = None,
) -> str:
    from app.api.routes.generate.jobs import _create_and_start_generation_job

    return await _create_and_start_generation_job(
        get_supabase(),
        TABLES,
        application_id=application_id,
        user_id=user_id,
        requested_modules=requested_modules,
        application_modules=application_modules,
    )


def _as_utc(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


class AutoPrepService:
    """Create prepared application workspaces from tracked discoveries."""

    def __init__(
        self,
        db: Optional[SupabaseDB] = None,
        *,
        scorer_factory: Optional[ScorerFactory] = None,
        jd_loader_factory: Optional[JDLoaderFactory] = None,
        job_creator: Optional[JobCreator] = None,
    ) -> None:
        self.db = db or get_db()
        self._scorer_factory = scorer_factory
        self._jd_loader_factory = jd_loader_factory or _shared_jd_loader
        self._job_creator = job_creator or _default_job_creator

    async def prepare_recent_discoveries(
        self,
        user_id: str,
        *,
        min_fit_score: float = AUTO_PREP_DEFAULT_MIN_FIT_SCORE,
        limit: int = AUTO_PREP_DEFAULT_LIMIT,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        if limit <= 0:
            return self._result(status="ok")
        if self._scorer_factory is None and not _is_live_enabled():
            return self._result(status="disabled", reason="live_scorer_disabled")

        tracked_rows = await self.db.query(
            TABLES["tracked_companies"],
            filters=[("user_id", "==", user_id), ("enabled", "==", True)],
            order_by="updated_at",
            order_direction="DESCENDING",
        )
        if not tracked_rows:
            return self._result(status="ok")

        tracked_names = {
            _clean_text(row.get("company_slug")).lower(): (
                _clean_text(row.get("display_name")) or _clean_text(row.get("company_slug"))
            )
            for row in tracked_rows
            if _clean_text(row.get("company_slug"))
        }
        if not tracked_names:
            return self._result(status="ok")

        discoveries = await self._load_recent_discoveries(tracked_names.keys(), now=now)
        if not discoveries:
            return self._result(status="ok")

        batch_id = make_batch_id()
        existing = await self._load_existing_dedup_keys(
            user_id=user_id,
            candidate_urls=[_clean_text(row.get("url_canonical") or row.get("url")) for row in discoveries],
        )

        candidate_rows: List[Mapping[str, Any]] = []
        entries: List[BatchEntry] = []
        rows_by_url: Dict[str, Mapping[str, Any]] = {}
        skipped_existing = 0

        for row in discoveries:
            canonical_url = _clean_text(row.get("url_canonical") or row.get("url"))
            if not canonical_url:
                continue
            dedup_key = make_dedup_key(user_id=user_id, canonical_url=canonical_url)
            if dedup_key in existing:
                skipped_existing += 1
                continue
            entry = BatchEntry(
                raw_url=canonical_url,
                canonical_url=canonical_url,
                ats_key=extract_ats_key(canonical_url),
            )
            candidate_rows.append(row)
            entries.append(entry)
            rows_by_url[canonical_url] = row

        if not entries:
            return self._result(
                status="ok",
                recent_discoveries=len(discoveries),
                skipped_existing=skipped_existing,
            )

        scorer = self._scorer_factory(user_id) if self._scorer_factory else _build_live_scorer(user_id)
        scored = await score_plan(
            entries,
            scorer=scorer,
            concurrency=min(DEFAULT_CONCURRENCY, max(1, len(entries))),
        )
        ranked = rank_batch(scored, min_fit_score=min_fit_score)
        jd_loader = self._jd_loader_factory()

        applications_created = 0
        jobs_queued = 0
        enrichment_failures = 0
        queue_failures = 0
        application_ids: List[str] = []
        job_ids: List[str] = []

        for result in ranked.ranked[:limit]:
            row = rows_by_url.get(result.canonical_url)
            if not row:
                continue

            entry = BatchEntry(
                raw_url=result.canonical_url,
                canonical_url=result.canonical_url,
                ats_key=extract_ats_key(result.canonical_url),
            )
            try:
                jd_text = await jd_loader(entry)
            except Exception as exc:
                enrichment_failures += 1
                logger.warning(
                    "auto_prep.jd_fetch_failed",
                    user_id=user_id,
                    canonical_url=result.canonical_url,
                    error=str(exc)[:200],
                )
                continue

            jd_text = _clean_text(jd_text)
            if not jd_text:
                enrichment_failures += 1
                continue

            title = (
                _clean_text(result.title)
                or _clean_text(row.get("role_title"))
                or _clean_text(row.get("title"))
            )
            slug = _clean_text(row.get("company_slug")).lower()
            company = _clean_text(result.company) or tracked_names.get(slug, _clean_text(row.get("company_slug")))

            hydrated_result = ScoringResult(
                canonical_url=result.canonical_url,
                fit_score=result.fit_score,
                error=result.error,
                title=title or result.title,
                company=company or result.company,
            )
            app_row = build_application_row(
                result=hydrated_result,
                user_id=user_id,
                batch_id=batch_id,
                now=now,
            )

            confirmed_facts = dict(app_row.get("confirmed_facts") or {})
            confirmed_facts.update(
                {
                    "source": "tracked_company_auto_prep",
                    "job_title": title or app_row.get("title"),
                    "jobTitle": title or app_row.get("title"),
                    "jd_text": jd_text,
                    "jdText": jd_text,
                    "company": company or None,
                    "auto_prep": {
                        "fit_score": result.fit_score,
                        "batch_id": batch_id,
                        "discovered_at": row.get("first_seen"),
                        "last_seen": row.get("last_seen"),
                        "company_slug": row.get("company_slug"),
                    },
                }
            )
            app_row["confirmed_facts"] = confirmed_facts
            if title:
                app_row["title"] = title

            app_id = await self.db.create(TABLES["applications"], dict(app_row))
            applications_created += 1
            application_ids.append(app_id)

            try:
                job_id = await self._job_creator(
                    application_id=app_id,
                    user_id=user_id,
                    requested_modules=list(AUTO_PREP_REQUESTED_MODULES),
                    application_modules=app_row.get("modules"),
                )
            except Exception as exc:
                queue_failures += 1
                logger.warning(
                    "auto_prep.job_queue_failed",
                    user_id=user_id,
                    application_id=app_id,
                    canonical_url=result.canonical_url,
                    error=str(exc)[:200],
                )
                continue

            jobs_queued += 1
            job_ids.append(job_id)

        return self._result(
            status="ok",
            recent_discoveries=len(discoveries),
            candidates_considered=len(entries),
            ranked_count=len(ranked.ranked),
            below_threshold=len(ranked.below_threshold),
            score_failures=len(ranked.failed),
            skipped_existing=skipped_existing,
            applications_created=applications_created,
            jobs_queued=jobs_queued,
            enrichment_failures=enrichment_failures,
            queue_failures=queue_failures,
            application_ids=application_ids,
            job_ids=job_ids,
        )

    async def _load_recent_discoveries(
        self,
        tracked_slugs: Any,
        *,
        now: datetime,
    ) -> List[Mapping[str, Any]]:
        cutoff = now - timedelta(hours=AUTO_PREP_DISCOVERY_WINDOW_HOURS)
        seen_urls: set[str] = set()
        rows: List[Mapping[str, Any]] = []

        for slug in tracked_slugs:
            recent = await self.db.query(
                TABLES["job_scan_history"],
                filters=[("company_slug", "==", slug)],
                order_by="last_seen",
                order_direction="DESCENDING",
                limit=AUTO_PREP_CANDIDATE_LIMIT,
            )
            for row in recent:
                last_seen = _as_utc(row.get("last_seen"))
                if last_seen is None or last_seen < cutoff:
                    continue
                canonical_url = _clean_text(row.get("url_canonical") or row.get("url"))
                if not canonical_url or canonical_url in seen_urls:
                    continue
                seen_urls.add(canonical_url)
                rows.append(row)

        rows.sort(
            key=lambda row: _as_utc(row.get("last_seen")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return rows[:AUTO_PREP_CANDIDATE_LIMIT]

    async def _load_existing_dedup_keys(
        self,
        *,
        user_id: str,
        candidate_urls: List[str],
    ) -> Dict[str, str]:
        candidate_keys = {
            make_dedup_key(user_id=user_id, canonical_url=url)
            for url in candidate_urls
            if url
        }
        if not candidate_keys:
            return {}

        existing_rows = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )
        existing: Dict[str, str] = {}
        for row in existing_rows:
            confirmed_facts = row.get("confirmed_facts") or {}
            if not isinstance(confirmed_facts, Mapping):
                continue
            key = _clean_text(confirmed_facts.get("dedup_key"))
            app_id = _clean_text(row.get("id"))
            if key and key in candidate_keys and app_id:
                existing[key] = app_id
        return existing

    @staticmethod
    def _result(status: str, **data: Any) -> Dict[str, Any]:
        return {
            "status": status,
            "recent_discoveries": 0,
            "candidates_considered": 0,
            "ranked_count": 0,
            "below_threshold": 0,
            "score_failures": 0,
            "skipped_existing": 0,
            "applications_created": 0,
            "jobs_queued": 0,
            "enrichment_failures": 0,
            "queue_failures": 0,
            "application_ids": [],
            "job_ids": [],
            **data,
        }


__all__ = [
    "AUTO_PREP_DEFAULT_LIMIT",
    "AUTO_PREP_DEFAULT_MIN_FIT_SCORE",
    "AUTO_PREP_REQUESTED_MODULES",
    "AutoPrepService",
]