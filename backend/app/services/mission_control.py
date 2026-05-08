"""Mission inbox sync + enrichment helpers.

Bridges the new M1 mission tables to the existing application corpus
without introducing the full orchestrator yet. The contract for this
slice is intentionally narrow:

* Sync existing user applications into ``mission_drafts`` using the
  mission's role targets, fit floor, and best-effort guardrails.
* Never auto-submit. Draft status only advances to ``ready_for_user``
  or ``sent`` based on existing application state.
* Enrich mission-draft responses with a small application snapshot so
  the frontend inbox can render real workspace metadata instead of raw
  UUIDs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from app.core.database import TABLES, SupabaseDB, get_db
from app.models.application_status import TERMINAL_STATUSES, UNAPPLIED_STATUSES, normalize_status

SYNC_TERMINAL_STATUS = "expired"
_DRAFT_STATUS_PRIORITY = {
    "surfaced": 0,
    "prepared": 1,
    "ready_for_user": 2,
    "sent": 3,
    "skipped": 4,
    "expired": 4,
}


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_phrase(value: Any) -> str:
    return _clean_text(value).lower()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = _clean_text(value)
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            cleaned = _clean_text(item)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
        return out
    return []


def _count_generated_documents(app: Mapping[str, Any]) -> int:
    generated = app.get("generated_documents") or {}
    if not isinstance(generated, Mapping):
        return 0
    return len([value for value in generated.values() if value])


def _has_review_signals(app: Mapping[str, Any]) -> bool:
    return bool(app.get("scorecard") or app.get("benchmark") or app.get("gaps"))


def _has_any_docs(app: Mapping[str, Any]) -> bool:
    return bool(
        app.get("cv_html")
        or app.get("resume_html")
        or app.get("cover_letter_html")
        or app.get("personal_statement_html")
        or app.get("portfolio_html")
        or _count_generated_documents(app)
    )


def is_ready_to_apply_application(app: Mapping[str, Any]) -> bool:
    status = normalize_status(str(app.get("status") or "")) or ""
    if status not in UNAPPLIED_STATUSES:
        return False

    has_primary_docs = bool(app.get("cv_html") or app.get("resume_html")) and bool(
        app.get("cover_letter_html")
        or app.get("personal_statement_html")
        or app.get("portfolio_html")
        or _count_generated_documents(app)
    )
    return has_primary_docs and _has_review_signals(app)


def _application_title(app: Mapping[str, Any]) -> str:
    confirmed_facts = _mapping(app.get("confirmed_facts"))
    return (
        _clean_text(confirmed_facts.get("jobTitle"))
        or _clean_text(confirmed_facts.get("job_title"))
        or _clean_text(confirmed_facts.get("title"))
        or _clean_text(app.get("job_title"))
        or _clean_text(app.get("title"))
        or "Untitled role"
    )


def _application_company(app: Mapping[str, Any]) -> str:
    confirmed_facts = _mapping(app.get("confirmed_facts"))
    return (
        _clean_text(confirmed_facts.get("company"))
        or _clean_text(app.get("company_name"))
        or _clean_text(app.get("company"))
        or "Unknown company"
    )


def _application_location_tokens(app: Mapping[str, Any]) -> list[str]:
    confirmed_facts = _mapping(app.get("confirmed_facts"))
    values: list[str] = []
    for candidate in (
        confirmed_facts.get("location"),
        confirmed_facts.get("locations"),
        app.get("location"),
        app.get("locations"),
        app.get("job_location"),
    ):
        values.extend(_string_list(candidate))
    return values


def _application_search_blob(app: Mapping[str, Any]) -> str:
    confirmed_facts = _mapping(app.get("confirmed_facts"))
    parts = [
        _application_title(app),
        _application_company(app),
        _clean_text(confirmed_facts.get("jd_text")),
        _clean_text(confirmed_facts.get("jdText")),
        _clean_text(app.get("document_strategy")),
    ]
    parts.extend(_application_location_tokens(app))
    return "\n".join(part for part in parts if part).lower()


def _application_fit_score(app: Mapping[str, Any]) -> Optional[float]:
    scores = _mapping(app.get("scores"))
    direct = scores.get("fit")
    if direct is None:
        auto_prep = _mapping(_mapping(app.get("confirmed_facts")).get("auto_prep"))
        direct = auto_prep.get("fit_score")
    if direct is None:
        return None
    try:
        return round(float(direct), 1)
    except (TypeError, ValueError):
        return None


def _role_matches(title: str, targets: Sequence[str]) -> bool:
    if not targets:
        return True
    normalized_title = _normalize_phrase(title)
    if not normalized_title:
        return False
    title_tokens = set(normalized_title.replace("/", " ").replace("-", " ").split())
    for target in targets:
        normalized_target = _normalize_phrase(target)
        if not normalized_target:
            continue
        if normalized_target in normalized_title or normalized_title in normalized_target:
            return True
        target_tokens = set(normalized_target.replace("/", " ").replace("-", " ").split())
        if target_tokens and target_tokens.issubset(title_tokens):
            return True
    return False


def _phrases_match_all(blob: str, phrases: Sequence[str]) -> bool:
    for phrase in phrases:
        normalized = _normalize_phrase(phrase)
        if normalized and normalized not in blob:
            return False
    return True


def _phrases_match_none(blob: str, phrases: Sequence[str]) -> bool:
    for phrase in phrases:
        normalized = _normalize_phrase(phrase)
        if normalized and normalized in blob:
            return False
    return True


def _location_matches(app: Mapping[str, Any], mission: Mapping[str, Any]) -> bool:
    mission_locations = _string_list(mission.get("locations"))
    if not mission_locations:
        return True
    location_blob = "\n".join(_application_location_tokens(app)).lower()
    if not location_blob:
        return True
    return any(_normalize_phrase(location) in location_blob for location in mission_locations)


def _mission_matches_application(app: Mapping[str, Any], mission: Mapping[str, Any]) -> bool:
    normalized_status = normalize_status(str(app.get("status") or "")) or ""
    if normalized_status in TERMINAL_STATUSES:
        return False

    fit_score = _application_fit_score(app)
    mission_floor = mission.get("min_fit_score")
    try:
        min_fit_score = float(mission_floor if mission_floor is not None else 0.0)
    except (TypeError, ValueError):
        min_fit_score = 0.0

    if fit_score is None and min_fit_score > 0:
        return False
    if fit_score is not None and fit_score < min_fit_score:
        return False

    if not _role_matches(_application_title(app), _string_list(mission.get("role_titles"))):
        return False
    if not _location_matches(app, mission):
        return False

    blob = _application_search_blob(app)
    if not _phrases_match_all(blob, _string_list(mission.get("must_haves"))):
        return False
    if not _phrases_match_none(blob, _string_list(mission.get("deal_breakers"))):
        return False
    return True


def _derived_draft_status(app: Mapping[str, Any]) -> str:
    normalized_status = normalize_status(str(app.get("status") or "")) or ""
    if normalized_status in TERMINAL_STATUSES:
        return SYNC_TERMINAL_STATUS
    if normalized_status and normalized_status not in UNAPPLIED_STATUSES:
        return "sent"
    if is_ready_to_apply_application(app):
        return "ready_for_user"
    if _has_any_docs(app) or _has_review_signals(app):
        return "prepared"
    return "surfaced"


def _merge_draft_status(existing_status: str, derived_status: str) -> str:
    existing = _normalize_phrase(existing_status) or "surfaced"
    derived = _normalize_phrase(derived_status) or "surfaced"
    if existing in {"skipped", "expired"}:
        return existing
    if derived == SYNC_TERMINAL_STATUS:
        return SYNC_TERMINAL_STATUS
    if existing == "sent":
        return existing
    if _DRAFT_STATUS_PRIORITY.get(derived, 0) > _DRAFT_STATUS_PRIORITY.get(existing, 0):
        return derived
    return existing


def _snapshot_application(app: Mapping[str, Any]) -> dict[str, Any]:
    confirmed_facts = _mapping(app.get("confirmed_facts"))
    return {
        "id": str(app.get("id") or ""),
        "title": _clean_text(app.get("title")) or _application_title(app),
        "role_title": _application_title(app),
        "company_name": _application_company(app),
        "status": normalize_status(str(app.get("status") or "")) or str(app.get("status") or ""),
        "updated_at": app.get("updated_at"),
        "fit_score": _application_fit_score(app),
        "source": _clean_text(confirmed_facts.get("source")) or None,
        "canonical_url": _clean_text(confirmed_facts.get("canonical_url")) or None,
        "company_slug": _clean_text(_mapping(confirmed_facts.get("auto_prep")).get("company_slug")) or None,
        "ready_to_apply": is_ready_to_apply_application(app),
        "generated_document_count": _count_generated_documents(app),
    }


class MissionControlService:
    MAX_SYNC_APPLICATIONS = 250
    MAX_SYNC_MISSIONS = 100

    def __init__(self, db: Optional[SupabaseDB] = None) -> None:
        self.db = db or get_db()

    async def list_enriched_drafts(
        self,
        mission: Mapping[str, Any],
        *,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        filters = [("mission_id", "==", str(mission.get("id") or ""))]
        if status is not None:
            filters.append(("status", "==", status))
        rows = await self.db.query(
            TABLES["mission_drafts"],
            filters=filters,
            order_by="surfaced_at",
            order_direction="DESCENDING",
            limit=max(1, min(limit, 200)),
        )
        return await self.enrich_drafts(rows, user_id=user_id)

    async def enrich_draft(self, draft: Mapping[str, Any], *, user_id: str) -> dict[str, Any]:
        rows = await self.enrich_drafts([draft], user_id=user_id)
        return rows[0] if rows else dict(draft)

    async def enrich_drafts(
        self,
        drafts: Iterable[Mapping[str, Any]],
        *,
        user_id: str,
    ) -> list[dict[str, Any]]:
        draft_rows = [dict(row) for row in drafts]
        application_ids = [str(row.get("application_id")) for row in draft_rows if row.get("application_id")]
        snapshots = await self._load_application_snapshots(application_ids, user_id=user_id)
        enriched: list[dict[str, Any]] = []
        for row in draft_rows:
            app_id = str(row.get("application_id") or "")
            enriched.append({
                **row,
                "application": snapshots.get(app_id),
            })
        return enriched

    async def sync_mission(
        self,
        mission: Mapping[str, Any],
        *,
        user_id: str,
        limit: int = MAX_SYNC_APPLICATIONS,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(limit, self.MAX_SYNC_APPLICATIONS))
        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
            order_by="updated_at",
            order_direction="DESCENDING",
            limit=safe_limit,
        )
        existing_drafts = await self.db.query(
            TABLES["mission_drafts"],
            filters=[("mission_id", "==", str(mission.get("id") or ""))],
            order_by=None,
        )

        existing_by_app_id = {
            str(row.get("application_id")): row
            for row in existing_drafts
            if row.get("application_id")
        }
        app_by_id = {
            str(app.get("id")): app
            for app in applications
            if app.get("id")
        }

        created = 0
        updated = 0
        matched = 0
        scanned = len(applications)
        now_iso = datetime.now(timezone.utc).isoformat()
        ready_for_user_promoted = 0

        for app in applications:
            app_id = str(app.get("id") or "")
            if not app_id:
                continue
            existing = existing_by_app_id.get(app_id)
            normalized_status = normalize_status(str(app.get("status") or "")) or ""

            if normalized_status in TERMINAL_STATUSES:
                if existing and existing.get("status") != SYNC_TERMINAL_STATUS:
                    await self.db.update(
                        TABLES["mission_drafts"],
                        str(existing.get("id") or ""),
                        {"status": SYNC_TERMINAL_STATUS},
                    )
                    updated += 1
                continue

            if not _mission_matches_application(app, mission):
                continue

            matched += 1
            fit_score = _application_fit_score(app)
            desired_status = _derived_draft_status(app)
            surfaced_at = str(app.get("updated_at") or now_iso)
            payload: dict[str, Any] = {
                "application_id": app_id,
                "fit_score": fit_score,
                "surfaced_at": surfaced_at,
            }

            if existing:
                existing_status = str(existing.get("status") or "surfaced")
                merged_status = _merge_draft_status(existing_status, desired_status)
                if merged_status == "ready_for_user" and existing_status != "ready_for_user":
                    ready_for_user_promoted += 1
                payload["status"] = merged_status
                if merged_status in {"prepared", "ready_for_user", "sent"}:
                    payload["prepared_at"] = existing.get("prepared_at") or surfaced_at
                if merged_status == "sent":
                    payload["sent_at"] = existing.get("sent_at") or surfaced_at

                update = {
                    key: value
                    for key, value in payload.items()
                    if existing.get(key) != value
                }
                if update:
                    await self.db.update(
                        TABLES["mission_drafts"],
                        str(existing.get("id") or ""),
                        update,
                    )
                    updated += 1
                continue

            payload["status"] = desired_status
            if desired_status == "ready_for_user":
                ready_for_user_promoted += 1
            if desired_status in {"prepared", "ready_for_user", "sent"}:
                payload["prepared_at"] = surfaced_at
            if desired_status == "sent":
                payload["sent_at"] = surfaced_at
            await self.db.create(
                TABLES["mission_drafts"],
                {"mission_id": str(mission.get("id") or ""), **payload},
            )
            created += 1

        enriched = await self.list_enriched_drafts(
            mission,
            user_id=user_id,
            limit=200,
        )
        return {
            "status": "ok",
            "mission_id": str(mission.get("id") or ""),
            "scanned_applications": scanned,
            "matched_applications": matched,
            "created": created,
            "updated": updated,
            "ready_for_user_promoted": ready_for_user_promoted,
            "ready_for_user_count": len([row for row in enriched if row.get("status") == "ready_for_user"]),
            "count": len(enriched),
        }

    async def sync_user_missions(
        self,
        user_id: str,
        *,
        statuses: Sequence[str] = ("active",),
        per_mission_limit: int = MAX_SYNC_APPLICATIONS,
    ) -> dict[str, Any]:
        normalized_statuses = [
            _normalize_phrase(status)
            for status in statuses
            if _normalize_phrase(status)
        ]
        filters: list[tuple[str, str, Any]] = [("user_id", "==", user_id)]
        if len(normalized_statuses) == 1:
            filters.append(("status", "==", normalized_statuses[0]))
        missions = await self.db.query(
            TABLES["missions"],
            filters=filters,
            order_by="created_at",
            order_direction="DESCENDING",
            limit=self.MAX_SYNC_MISSIONS,
        )

        synced = 0
        created = 0
        updated = 0
        matched = 0
        scanned = 0
        total_drafts = 0
        ready_for_user_promoted = 0
        ready_for_user_count = 0

        for mission in missions:
            if normalized_statuses and _normalize_phrase(mission.get("status")) not in normalized_statuses:
                continue
            summary = await self.sync_mission(
                mission,
                user_id=user_id,
                limit=per_mission_limit,
            )
            synced += 1
            created += int(summary.get("created") or 0)
            updated += int(summary.get("updated") or 0)
            matched += int(summary.get("matched_applications") or 0)
            scanned += int(summary.get("scanned_applications") or 0)
            total_drafts += int(summary.get("count") or 0)
            ready_for_user_promoted += int(summary.get("ready_for_user_promoted") or 0)
            ready_for_user_count += int(summary.get("ready_for_user_count") or 0)

        return {
            "status": "ok",
            "missions_considered": len(missions),
            "missions_synced": synced,
            "created": created,
            "updated": updated,
            "matched_applications": matched,
            "scanned_applications": scanned,
            "draft_count": total_drafts,
            "ready_for_user_promoted": ready_for_user_promoted,
            "ready_for_user_count": ready_for_user_count,
        }

    async def _load_application_snapshots(
        self,
        application_ids: Sequence[str],
        *,
        user_id: str,
    ) -> dict[str, dict[str, Any]]:
        ids = [str(value) for value in application_ids if value]
        if not ids:
            return {}
        rows = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id), ("id", "in", ids)],
            order_by=None,
        )
        return {
            str(row.get("id") or ""): _snapshot_application(row)
            for row in rows
            if row.get("id")
        }


__all__ = [
    "MissionControlService",
    "SYNC_TERMINAL_STATUS",
    "is_ready_to_apply_application",
]