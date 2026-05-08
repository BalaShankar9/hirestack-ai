"""Cadence dashboard service.

Bridges the pure cadence primitives to the user-facing dashboard route.
This service is read-only: it computes today's actionable cadence view
from ``applications`` plus any existing ``application_followups`` rows.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from app.core.database import TABLES, SupabaseDB, get_db
from app.models.application_status import TERMINAL_STATUSES, normalize_status
from app.services.cadence_engine import FollowupBeat, _coerce_dt, next_followup_beat
from app.services.followup_drafter import FollowupDraft, render_followup_draft


class CadenceService:
    """Compute the dashboard cadence buckets for one user."""

    def __init__(self, db: Optional[SupabaseDB] = None) -> None:
        self.db = db or get_db()

    async def compute_dashboard(
        self,
        user_id: str,
        *,
        user_context: Optional[Mapping[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> dict[str, Any]:
        now_utc = now or datetime.now(timezone.utc)
        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
            order_by="updated_at",
            order_direction="DESCENDING",
            limit=250,
        )

        try:
            followups = await self.db.query(
                TABLES["application_followups"],
                filters=[("user_id", "==", user_id)],
                order_by="scheduled_for",
                order_direction="ASCENDING",
                limit=1000,
            )
        except Exception:
            followups = []

        followups_by_app: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in followups:
            app_id = row.get("application_id")
            if app_id:
                followups_by_app[str(app_id)].append(row)

        buckets: dict[str, list[dict[str, Any]]] = {
            "urgent": [],
            "overdue": [],
            "waiting": [],
            "cold": [],
        }
        closed_count = 0

        for application in applications:
            status = normalize_status(str(application.get("status") or "")) or ""
            if status in TERMINAL_STATUSES:
                closed_count += 1
                continue

            item = self._classify_application(
                application,
                followups_by_app.get(str(application.get("id") or ""), []),
                now=now_utc,
                user_context=user_context,
            )
            if item is None:
                continue
            buckets[item.pop("bucket")].append(item)

        for key in ("urgent", "overdue", "waiting"):
            buckets[key].sort(
                key=lambda item: (
                    item.get("scheduled_for") or "",
                    item.get("company") or "",
                    item.get("role") or "",
                )
            )
        buckets["cold"].sort(
            key=lambda item: (
                -(item.get("followup_count") or 0),
                item.get("company") or "",
                item.get("role") or "",
            )
        )

        counts = {key: len(value) for key, value in buckets.items()}
        return {
            "date": now_utc.date().isoformat(),
            "buckets": buckets,
            "metadata": {
                "total_tracked": len(applications),
                "actionable_count": counts["urgent"] + counts["overdue"],
                "urgent_count": counts["urgent"],
                "overdue_count": counts["overdue"],
                "waiting_count": counts["waiting"],
                "cold_count": counts["cold"],
                "closed_count": closed_count,
            },
        }

    def _classify_application(
        self,
        application: Mapping[str, Any],
        history: list[Mapping[str, Any]],
        *,
        now: datetime,
        user_context: Optional[Mapping[str, Any]],
    ) -> Optional[dict[str, Any]]:
        status = normalize_status(str(application.get("status") or "")) or ""
        response_at = _coerce_dt(application.get("response_received_at"))
        active_row = self._active_followup_row(history)
        sent_count = self._sent_followup_count(history)

        if active_row is not None:
            beat = self._beat_from_row(active_row)
            draft = self._draft_from_row(active_row)
            scheduled_for = _coerce_dt(active_row.get("scheduled_for"))
            followup_count = int(active_row.get("followup_count") or beat.followup_count)
        else:
            beat = next_followup_beat(application, history=history, now=now)
            if beat is None and response_at is None and status in {"submitted", "active"} and sent_count >= 2:
                return self._build_item(
                    application,
                    bucket="cold",
                    now=now,
                    followup_count=sent_count,
                    beat=None,
                    scheduled_for=None,
                    draft=None,
                )
            if beat is None:
                return None
            draft = self._render_draft(beat, application, user_context)
            scheduled_for = beat.scheduled_for
            followup_count = beat.followup_count

        if response_at is None and (sent_count >= 2 or (beat and beat.template_key == "cold_reopen")):
            bucket = "cold"
        elif scheduled_for is not None and scheduled_for < now:
            bucket = "urgent" if status in {"responded", "interview"} else "overdue"
        elif status in {"responded", "interview"} and scheduled_for is not None and scheduled_for <= now + timedelta(days=1):
            bucket = "urgent"
        else:
            bucket = "waiting"

        return self._build_item(
            application,
            bucket=bucket,
            now=now,
            followup_count=followup_count,
            beat=beat,
            scheduled_for=scheduled_for,
            draft=draft,
            followup_id=str(active_row.get("id")) if active_row and active_row.get("id") else None,
        )

    def _build_item(
        self,
        application: Mapping[str, Any],
        *,
        bucket: str,
        now: datetime,
        followup_count: int,
        beat: Optional[FollowupBeat],
        scheduled_for: Optional[datetime],
        draft: Optional[FollowupDraft | Mapping[str, Any]],
        followup_id: Optional[str] = None,
    ) -> dict[str, Any]:
        company = self._company_name(application)
        role = self._role_title(application)
        status = normalize_status(str(application.get("status") or "")) or ""
        days_until = None
        days_overdue = None
        if scheduled_for is not None:
            day_delta = (scheduled_for.date() - now.date()).days
            if scheduled_for < now:
                days_overdue = max((now.date() - scheduled_for.date()).days, 0)
            else:
                days_until = max(day_delta, 0)

        if isinstance(draft, FollowupDraft):
            draft_subject = draft.subject
            draft_body = draft.body
            placeholders = list(draft.placeholders_missing)
        elif isinstance(draft, Mapping):
            draft_subject = draft.get("subject")
            draft_body = draft.get("body")
            placeholders = list(draft.get("placeholders_missing") or [])
        else:
            draft_subject = None
            draft_body = None
            placeholders = []

        return {
            "bucket": bucket,
            "id": str(application.get("id") or ""),
            "application_id": str(application.get("id") or ""),
            "followup_id": followup_id,
            "company": company,
            "role": role,
            "status": status,
            "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
            "days_until": days_until,
            "days_overdue": days_overdue,
            "followup_count": followup_count,
            "template_key": beat.template_key if beat else None,
            "suggested_channel": beat.channel if beat else None,
            "reason": beat.reason if beat else "Two or more follow-ups sent with no response.",
            "draft_subject": draft_subject,
            "draft_body": draft_body,
            "draft_placeholders_missing": placeholders,
        }

    @staticmethod
    def _active_followup_row(history: list[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
        candidates: list[tuple[datetime, Mapping[str, Any]]] = []
        for row in history:
            if row.get("dismissed_at"):
                continue
            status = str(row.get("status") or "")
            if status not in {"pending", "draft_ready"}:
                continue
            scheduled_for = _coerce_dt(row.get("scheduled_for"))
            if scheduled_for is None:
                continue
            candidates.append((scheduled_for, row))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    @staticmethod
    def _sent_followup_count(history: list[Mapping[str, Any]]) -> int:
        count = 0
        for row in history:
            status = str(row.get("status") or "")
            if row.get("sent_at") or status in {"sent", "responded"}:
                count += 1
        return count

    @staticmethod
    def _beat_from_row(row: Mapping[str, Any]) -> FollowupBeat:
        scheduled_for = _coerce_dt(row.get("scheduled_for")) or datetime.now(timezone.utc)
        return FollowupBeat(
            template_key=str(row.get("template_key") or "first"),
            scheduled_for=scheduled_for,
            channel=str(row.get("channel") or "email"),
            followup_count=int(row.get("followup_count") or 1),
            reason=str(row.get("reason") or "Existing follow-up beat."),
        )

    @staticmethod
    def _draft_from_row(row: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        draft = row.get("draft")
        if isinstance(draft, Mapping):
            return draft
        return None

    def _render_draft(
        self,
        beat: FollowupBeat,
        application: Mapping[str, Any],
        user_context: Optional[Mapping[str, Any]],
    ) -> Optional[FollowupDraft]:
        try:
            return render_followup_draft(
                beat,
                {
                    "company_name": self._company_name(application),
                    "role_title": self._role_title(application),
                    "contact_name": str(application.get("contact_name") or ""),
                    "contact_email": str(application.get("contact_email") or ""),
                    "contact_linkedin": str(application.get("contact_linkedin") or ""),
                    "user_first_name": self._user_first_name(user_context),
                },
            )
        except ValueError:
            return None

    @staticmethod
    def _company_name(application: Mapping[str, Any]) -> str:
        return str(
            application.get("company_name")
            or application.get("company")
            or "Unknown company"
        )

    @staticmethod
    def _role_title(application: Mapping[str, Any]) -> str:
        return str(
            application.get("job_title")
            or application.get("title")
            or "Untitled role"
        )

    @staticmethod
    def _user_first_name(user_context: Optional[Mapping[str, Any]]) -> str:
        if not user_context:
            return ""
        full_name = str(
            user_context.get("full_name")
            or user_context.get("name")
            or user_context.get("email", "")
        ).strip()
        if not full_name:
            return ""
        return full_name.split()[0]


__all__ = ["CadenceService"]