"""AIM source-library service.

This is the first durable foundation for source-backed academic work. It stores
source cards with enough metadata to support later citation verification without
pretending a source is fully verified at creation time.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from app.core.database import SupabaseDB, TABLES, get_db


SOURCE_TYPES: frozenset[str] = frozenset({
    "assignment_brief",
    "rubric",
    "lecture_notes",
    "journal_article",
    "book",
    "book_chapter",
    "textbook",
    "official_statistics",
    "standard",
    "government_report",
    "ngo_report",
    "institution_report",
    "industry_report",
    "company_report",
    "trade_publication",
    "news",
    "dataset",
    "web_page",
    "blog",
    "image_figure",
    "user_notes",
    "other",
})

RELIABILITY_TIERS: frozenset[str] = frozenset({
    "tier_1",
    "tier_2",
    "tier_3",
    "tier_4",
    "blocked",
})

VERIFICATION_STATUSES: frozenset[str] = frozenset({
    "needs_metadata",
    "unverified",
    "verified",
    "blocked",
})

_SOURCE_TYPE_TIERS: dict[str, str] = {
    "journal_article": "tier_1",
    "book": "tier_1",
    "book_chapter": "tier_1",
    "textbook": "tier_1",
    "official_statistics": "tier_1",
    "standard": "tier_1",
    "government_report": "tier_2",
    "ngo_report": "tier_2",
    "institution_report": "tier_2",
    "industry_report": "tier_2",
    "company_report": "tier_3",
    "trade_publication": "tier_3",
    "news": "tier_3",
    "dataset": "tier_3",
    "assignment_brief": "tier_4",
    "rubric": "tier_4",
    "lecture_notes": "tier_4",
    "web_page": "tier_4",
    "blog": "tier_4",
    "image_figure": "tier_4",
    "user_notes": "tier_4",
    "other": "tier_4",
}


class AIMSourceService:
    def __init__(self, db: Optional[SupabaseDB] = None) -> None:
        self.db = db or get_db()

    async def create_source(
        self,
        user_id: str,
        assignment_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        assignment = await self._get_owned_assignment(user_id, assignment_id)
        if not assignment:
            raise ValueError("assignment not found")

        row = self._build_source_row(user_id, assignment_id, payload)
        new_id = await self.db.create(TABLES["aim_sources"], row)
        row["id"] = new_id
        return row

    async def list_sources(self, user_id: str, assignment_id: str) -> list[dict[str, Any]]:
        assignment = await self._get_owned_assignment(user_id, assignment_id)
        if not assignment:
            raise ValueError("assignment not found")
        return await self.db.query(
            TABLES["aim_sources"],
            filters=[("assignment_id", "==", assignment_id), ("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
        )

    async def get_source(self, user_id: str, source_id: str) -> Optional[dict[str, Any]]:
        row = await self.db.get(TABLES["aim_sources"], source_id)
        if not row or row.get("user_id") != user_id:
            return None
        return row

    async def delete_source(self, user_id: str, source_id: str) -> bool:
        existing = await self.get_source(user_id, source_id)
        if not existing:
            return False
        return await self.db.delete(TABLES["aim_sources"], source_id)

    async def _get_owned_assignment(
        self,
        user_id: str,
        assignment_id: str,
    ) -> Optional[dict[str, Any]]:
        row = await self.db.get(TABLES["aim_assignments"], assignment_id)
        if not row or row.get("user_id") != user_id:
            return None
        return row

    def _build_source_row(
        self,
        user_id: str,
        assignment_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
        source_type = _normalize_source_type(payload.get("source_type"))
        reliability_tier = _normalize_reliability_tier(
            payload.get("reliability_tier") or metadata.get("reliability_tier"),
            source_type,
        )
        verification_status = _normalize_verification_status(
            payload.get("verification_status") or metadata.get("verification_status"),
            reliability_tier=reliability_tier,
            title=_clean(payload.get("title")),
            doi=_clean(payload.get("doi")),
            url=_clean(payload.get("url")),
            raw_text=_clean(payload.get("raw_text")),
        )
        now = datetime.now(timezone.utc).isoformat()
        return {
            "assignment_id": assignment_id,
            "user_id": user_id,
            "source_type": source_type,
            "title": _clean(payload.get("title")) or None,
            "authors": _clean_str_list(payload.get("authors")),
            "year": _coerce_year(payload.get("year")),
            "publisher": _clean(payload.get("publisher")) or None,
            "journal": _clean(payload.get("journal")) or None,
            "doi": _clean(payload.get("doi")) or None,
            "url": _clean(payload.get("url")) or None,
            "access_date": _clean(payload.get("access_date")) or None,
            "reliability_tier": reliability_tier,
            "verification_status": verification_status,
            "raw_text": _clean(payload.get("raw_text")) or None,
            "extracted_summary": _clean(payload.get("extracted_summary")) or None,
            "relevant_quotes": _clean_quote_list(payload.get("relevant_quotes")),
            "metadata": dict(metadata),
            "created_at": now,
            "updated_at": now,
        }


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _clean_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = _clean(item)
        key = cleaned.lower()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _clean_quote_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    out: list[Any] = []
    for item in value:
        if isinstance(item, str):
            cleaned = _clean(item)
            if cleaned:
                out.append(cleaned)
        elif isinstance(item, Mapping):
            out.append(dict(item))
    return out


def _coerce_year(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    if year < 0 or year > 9999:
        return None
    return year


def _normalize_source_type(value: Any) -> str:
    source_type = _clean(value).lower().replace("-", "_") or "other"
    return source_type if source_type in SOURCE_TYPES else "other"


def _normalize_reliability_tier(value: Any, source_type: str) -> str:
    tier = _clean(value).lower().replace(" ", "_")
    if tier in RELIABILITY_TIERS:
        return tier
    return _SOURCE_TYPE_TIERS.get(source_type, "tier_4")


def _normalize_verification_status(
    value: Any,
    *,
    reliability_tier: str,
    title: str,
    doi: str,
    url: str,
    raw_text: str,
) -> str:
    status_value = _clean(value).lower().replace(" ", "_")
    if status_value in VERIFICATION_STATUSES:
        return status_value
    if reliability_tier == "blocked":
        return "blocked"
    if not title or not (doi or url or raw_text):
        return "needs_metadata"
    return "unverified"


__all__ = [
    "AIMSourceService",
    "RELIABILITY_TIERS",
    "SOURCE_TYPES",
    "VERIFICATION_STATUSES",
]