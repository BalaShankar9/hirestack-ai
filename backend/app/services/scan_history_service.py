"""Scan-history service — dedup + repost detection for ghost-job signal.

Backs the ``job_scan_history`` table. Every time a URL is scanned
(via public ``/ghost-check`` or authenticated ``/intel/legitimacy``)
this service:

  1. Canonicalizes the URL (strips tracking params, normalizes host/path).
  2. Either inserts a new row or increments ``times_seen`` on the
     existing row and updates ``last_seen``.
  3. Returns a dict the caller feeds into ``PostingLegitimacyChain``:

        {
            "times_seen":  int,
            "first_seen":  iso8601,
            "last_seen":   iso8601,
            "days_span":   int,       # now() - first_seen in days
            "is_repost":   bool,      # times_seen >= 2 AND days_span >= 90
        }

The repost heuristic matches career-ops's Block G reposting rule:
"if the same posting shows up again 3+ months later, it's more likely
to be a ghost job or evergreen req farming."

This is a GLOBAL table (no RLS) — rows are shared across users so
repost detection benefits from fleet-wide scan coverage. Only the
backend's service-role key writes to it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from app.services.url_canonicalizer import canonicalize_url

logger = structlog.get_logger("hirestack.scan_history")

# Repost heuristic thresholds (see module docstring).
_REPOST_MIN_SEEN = 2
_REPOST_MIN_DAYS_SPAN = 90


class ScanHistoryService:
    """Dedup + repost tracker for job postings."""

    def __init__(self, db: Any) -> None:
        """``db`` must be a Supabase client supporting the fluent chain
        ``.table(...).select(...).eq(...).execute()``. The raw
        ``supabase.Client`` returned by ``get_supabase()`` works as-is.
        """
        self.db = db

    # ── public API ────────────────────────────────────────────────────────

    def record_scan(
        self,
        url: str,
        *,
        company_slug: str,
        role_title: str,
    ) -> dict[str, Any]:
        """Record a scan and return its repost signal.

        Raises no exceptions on transient DB faults — on error returns the
        "first-scan" dict so the caller can degrade gracefully.
        """
        canonical = canonicalize_url(url)
        slug = (company_slug or "unknown").strip().lower() or "unknown"
        role = (role_title or "").strip()
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        try:
            existing = self._fetch_existing(canonical)
        except Exception as exc:  # noqa: BLE001 — degrade gracefully
            logger.warning("scan_history.fetch_failed", error=str(exc)[:200])
            existing = None

        if existing:
            return self._increment_existing(existing, now, now_iso)

        return self._create_new(canonical, slug, role, now_iso)

    # ── internals ─────────────────────────────────────────────────────────

    def _fetch_existing(self, canonical: str) -> Optional[dict[str, Any]]:
        result = (
            self.db.table("job_scan_history")
            .select("*")
            .eq("url_canonical", canonical)
            .execute()
        )
        data = getattr(result, "data", None) or []
        return data[0] if data else None

    def _increment_existing(
        self,
        existing: dict[str, Any],
        now: datetime,
        now_iso: str,
    ) -> dict[str, Any]:
        times_seen = int(existing.get("times_seen", 1)) + 1
        first_seen_raw = existing.get("first_seen")

        days_span = 0
        if isinstance(first_seen_raw, str):
            try:
                # ISO 8601 with optional trailing Z
                first_dt = datetime.fromisoformat(
                    first_seen_raw.replace("Z", "+00:00")
                )
                if first_dt.tzinfo is None:
                    first_dt = first_dt.replace(tzinfo=timezone.utc)
                days_span = max((now - first_dt).days, 0)
            except (ValueError, TypeError):
                days_span = 0

        try:
            (
                self.db.table("job_scan_history")
                .update({"last_seen": now_iso, "times_seen": times_seen})
                .eq("id", existing["id"])
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan_history.update_failed", error=str(exc)[:200])

        is_repost = (
            times_seen >= _REPOST_MIN_SEEN
            and days_span >= _REPOST_MIN_DAYS_SPAN
        )

        return {
            "times_seen": times_seen,
            "first_seen": first_seen_raw,
            "last_seen": now_iso,
            "days_span": days_span,
            "is_repost": is_repost,
        }

    def _create_new(
        self,
        canonical: str,
        company_slug: str,
        role_title: str,
        now_iso: str,
    ) -> dict[str, Any]:
        payload = {
            "url_canonical": canonical,
            "company_slug": company_slug,
            "role_title": role_title,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "times_seen": 1,
        }
        try:
            (
                self.db.table("job_scan_history")
                .upsert(payload, on_conflict="url_canonical")
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("scan_history.upsert_failed", error=str(exc)[:200])

        return {
            "times_seen": 1,
            "first_seen": now_iso,
            "last_seen": now_iso,
            "days_span": 0,
            "is_repost": False,
        }


__all__ = ["ScanHistoryService"]
