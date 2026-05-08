"""Morning brief preview assembly.

Builds a dashboard-safe preview from the pure ``compose_morning_brief``
composer without sending email or depending on cron/transport slices.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from app.core.database import TABLES, SupabaseDB, get_db
from app.models.application_status import TERMINAL_STATUSES, UNAPPLIED_STATUSES, normalize_status
from app.services.cadence import CadenceService
from app.services.cadence_engine import _coerce_dt
from app.services.morning_brief import (
    BeatItem,
    JobItem,
    MorningBriefInputs,
    ReadyItem,
    StaleItem,
    WinItem,
    compose_morning_brief,
)


class MorningBriefPreviewService:
    def __init__(
        self,
        db: Optional[SupabaseDB] = None,
        cadence_service: Optional[CadenceService] = None,
    ) -> None:
        self.db = db or get_db()
        self.cadence_service = cadence_service or CadenceService(db=self.db)

    async def build_preview(
        self,
        user_id: str,
        *,
        user_context: Optional[Mapping[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> Optional[dict[str, Any]]:
        now_utc = now or datetime.now(timezone.utc)
        apps = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
            order_by="updated_at",
            order_direction="DESCENDING",
            limit=250,
        )
        apps_by_id = {str(app.get("id")): app for app in apps if app.get("id")}

        cadence = await self.cadence_service.compute_dashboard(
            user_id,
            user_context=user_context,
            now=now_utc,
        )
        ready = self._load_ready_to_apply(apps)
        beats_today = self._beats_from_cadence(cadence)
        new_jobs = await self._load_new_jobs(user_id, now_utc)
        stale = self._load_stale_applications(apps, now_utc)
        wins = await self._load_wins(user_id, apps_by_id, now_utc)

        inputs = MorningBriefInputs(
            user_first_name=self._user_first_name(user_context),
            brief_date=now_utc.date(),
            ready_to_apply=ready,
            beats_today=beats_today,
            new_jobs=new_jobs,
            stale_applications=stale,
            wins_yesterday=wins,
        )
        brief = compose_morning_brief(inputs)
        if brief.is_empty():
            return None

        summary = self._summary_text(brief.section_counts)
        action_label, action_href = self._action_target(brief.section_counts)
        return {
            "source": "morning_brief",
            "is_empty": False,
            "subject": brief.subject,
            "insight": brief.nudge or summary,
            "summary": summary,
            "body_text": brief.body_text,
            "body_html": brief.body_html,
            "section_counts": dict(brief.section_counts),
            "nudge": brief.nudge,
            "action_label": action_label,
            "action_href": action_href,
        }

    @staticmethod
    def _load_ready_to_apply(apps: list[Mapping[str, Any]]) -> tuple[ReadyItem, ...]:
        ready: list[tuple[datetime, ReadyItem]] = []
        for app in apps:
            status = normalize_status(str(app.get("status") or "")) or ""
            if status not in UNAPPLIED_STATUSES:
                continue

            generated_documents = app.get("generated_documents") or {}
            generated_count = len([value for value in generated_documents.values() if value]) if isinstance(generated_documents, Mapping) else 0
            has_review_signals = bool(app.get("scorecard") or app.get("benchmark") or app.get("gaps"))
            has_primary_docs = bool(app.get("cv_html") or app.get("resume_html")) and bool(
                app.get("cover_letter_html")
                or app.get("personal_statement_html")
                or app.get("portfolio_html")
                or generated_count
            )
            if not (has_primary_docs and has_review_signals):
                continue

            confirmed_facts = app.get("confirmed_facts") or {}
            if not isinstance(confirmed_facts, Mapping):
                confirmed_facts = {}
            company = str(
                confirmed_facts.get("company")
                or app.get("company_name")
                or app.get("company")
                or "Unknown company"
            )
            role = str(
                confirmed_facts.get("jobTitle")
                or confirmed_facts.get("job_title")
                or app.get("job_title")
                or app.get("title")
                or "Untitled role"
            )
            updated_at = _coerce_dt(app.get("updated_at")) or datetime.fromtimestamp(0, tz=timezone.utc)
            ready.append(
                (
                    updated_at,
                    ReadyItem(
                        company_name=company,
                        role_title=role,
                        application_id=str(app.get("id") or ""),
                    ),
                )
            )

        ready.sort(key=lambda item: item[0], reverse=True)
        return tuple(item for _, item in ready[:5])

    @staticmethod
    def _beats_from_cadence(cadence: Mapping[str, Any]) -> tuple[BeatItem, ...]:
        items: list[BeatItem] = []
        buckets = cadence.get("buckets") or {}
        for bucket in ("urgent", "overdue", "waiting"):
            for item in buckets.get(bucket) or []:
                days_until = item.get("days_until")
                if bucket == "waiting" and days_until not in (0, None):
                    continue
                items.append(
                    BeatItem(
                        company_name=str(item.get("company") or "Unknown company"),
                        role_title=str(item.get("role") or "Untitled role"),
                        template_key=str(item.get("template_key") or "first"),
                        application_id=str(item.get("application_id") or ""),
                    )
                )
        return tuple(items[:5])

    async def _load_new_jobs(self, user_id: str, now: datetime) -> tuple[JobItem, ...]:
        tracked_rows = await self.db.query(
            TABLES["tracked_companies"],
            filters=[("user_id", "==", user_id)],
            order_by=None,
        )
        slugs = sorted(
            {
                str(row.get("company_slug", "")).strip()
                for row in tracked_rows
                if row.get("company_slug")
            }
        )
        if not slugs:
            return ()

        cutoff = (now - timedelta(days=2)).isoformat()
        rows = await self.db.query(
            TABLES["job_scan_history"],
            filters=[("company_slug", "in", slugs), ("last_seen", ">=", cutoff)],
            order_by="last_seen",
            order_direction="DESCENDING",
            limit=5,
        )
        display_name_by_slug = {
            str(row["company_slug"]): row.get("display_name") or row["company_slug"]
            for row in tracked_rows
            if row.get("company_slug")
        }

        jobs: list[JobItem] = []
        for row in rows:
            last_seen = _coerce_dt(row.get("last_seen"))
            posted_within_days = None
            if last_seen is not None:
                posted_within_days = max((now.date() - last_seen.date()).days, 0)
            slug = str(row.get("company_slug") or "")
            jobs.append(
                JobItem(
                    company_name=str(display_name_by_slug.get(slug, slug or "Unknown company")),
                    role_title=str(row.get("role_title") or "Untitled role"),
                    url=str(row.get("url_canonical") or row.get("url") or ""),
                    posted_within_days=posted_within_days,
                )
            )
        return tuple(jobs)

    @staticmethod
    def _load_stale_applications(apps: list[Mapping[str, Any]], now: datetime) -> tuple[StaleItem, ...]:
        stale: list[StaleItem] = []
        for app in apps:
            status = normalize_status(str(app.get("status") or "")) or ""
            if status in TERMINAL_STATUSES:
                continue
            anchor = (
                _coerce_dt(app.get("updated_at"))
                or _coerce_dt(app.get("response_received_at"))
                or _coerce_dt(app.get("submitted_at"))
                or _coerce_dt(app.get("created_at"))
            )
            if anchor is None:
                continue
            days_silent = (now.date() - anchor.date()).days
            if days_silent < 14:
                continue
            stale.append(
                StaleItem(
                    company_name=str(app.get("company_name") or app.get("company") or "Unknown company"),
                    role_title=str(app.get("job_title") or app.get("title") or "Untitled role"),
                    days_silent=days_silent,
                    application_id=str(app.get("id") or ""),
                )
            )
        stale.sort(key=lambda item: item.days_silent, reverse=True)
        return tuple(stale[:5])

    async def _load_wins(
        self,
        user_id: str,
        apps_by_id: Mapping[str, Mapping[str, Any]],
        now: datetime,
    ) -> tuple[WinItem, ...]:
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        yesterday_start = today_start - timedelta(days=1)
        signal_rows = await self.db.query(
            TABLES["outcome_signals"],
            filters=[
                ("user_id", "==", user_id),
                ("created_at", ">=", yesterday_start.isoformat()),
                ("created_at", "<", today_start.isoformat()),
                ("signal_type", "in", ["screened", "interview", "offer", "accepted"]),
            ],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=10,
        )

        wins: list[WinItem] = []
        seen_app_ids: set[str] = set()
        for row in signal_rows:
            app_id = str(row.get("application_id") or "")
            app = apps_by_id.get(app_id)
            if not app:
                continue
            seen_app_ids.add(app_id)
            signal_type = str(row.get("signal_type") or "response")
            kind = "response" if signal_type == "screened" else ("offer" if signal_type == "accepted" else signal_type)
            wins.append(
                WinItem(
                    company_name=str(app.get("company_name") or app.get("company") or "Unknown company"),
                    role_title=str(app.get("job_title") or app.get("title") or "Untitled role"),
                    kind=kind,
                )
            )

        for app_id, app in apps_by_id.items():
            if app_id in seen_app_ids:
                continue
            response_at = _coerce_dt(app.get("response_received_at"))
            if response_at is None or not (yesterday_start <= response_at < today_start):
                continue
            wins.append(
                WinItem(
                    company_name=str(app.get("company_name") or app.get("company") or "Unknown company"),
                    role_title=str(app.get("job_title") or app.get("title") or "Untitled role"),
                    kind="response",
                )
            )

        return tuple(wins[:5])

    @staticmethod
    def _summary_text(section_counts: Mapping[str, int]) -> str:
        parts: list[str] = []
        if section_counts.get("ready"):
            count = int(section_counts["ready"])
            parts.append(f"{count} ready")
        if section_counts.get("beats"):
            count = int(section_counts["beats"])
            parts.append(f"{count} follow-up{'s' if count != 1 else ''} due")
        if section_counts.get("jobs"):
            count = int(section_counts["jobs"])
            parts.append(f"{count} new role{'s' if count != 1 else ''}")
        if section_counts.get("stale"):
            count = int(section_counts["stale"])
            parts.append(f"{count} stale app{'s' if count != 1 else ''}")
        if section_counts.get("wins"):
            count = int(section_counts["wins"])
            parts.append(f"{count} win{'s' if count != 1 else ''}")
        return "; ".join(parts) if parts else "Quiet day — nothing needs a briefing."

    @staticmethod
    def _action_target(section_counts: Mapping[str, int]) -> tuple[str, str]:
        if section_counts.get("beats"):
            return ("Review cadence", "/dashboard")
        if section_counts.get("ready"):
            return ("Review ready drafts", "/dashboard")
        if section_counts.get("jobs"):
            return ("Check discoveries", "/tracked-companies")
        if section_counts.get("stale"):
            return ("Open applications", "/dashboard")
        if section_counts.get("wins"):
            return ("See progress", "/career-analytics")
        return ("Open dashboard", "/dashboard")

    @staticmethod
    def _user_first_name(user_context: Optional[Mapping[str, Any]]) -> str:
        if not user_context:
            return "there"
        value = str(
            user_context.get("full_name")
            or user_context.get("name")
            or user_context.get("email")
            or "there"
        ).strip()
        if not value:
            return "there"
        return value.split()[0]


__all__ = ["MorningBriefPreviewService"]