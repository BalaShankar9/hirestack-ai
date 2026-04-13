"""
Autonomous Career Monitor — proactive intelligence engine.

Detects staleness, decay, opportunities, and regressions BEFORE the user
notices, then creates actionable career_alerts with direct action paths.

Alert types:
  - profile_stale: Profile hasn't been updated in N days
  - evidence_decay: Evidence confidence scores are dropping below threshold
  - skill_trending: A skill in the user's profile is trending in job market
  - market_shift: Significant changes in demand for user's target roles
  - document_outdated: Documents generated >30 days ago with stale evidence
  - quality_regression: Pipeline quality scores dropped significantly
  - opportunity_match: New saved job closely matches user's strengthened profile
  - interview_prep_reminder: Upcoming interview detected, prep materials not generated
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger("hirestack.career_monitor")


class AutonomousCareerMonitor:
    """Proactive career intelligence daemon.

    Runs periodic scans per-user (triggered via API or background worker)
    and creates career_alerts for anything that needs attention.
    """

    # Thresholds
    PROFILE_STALE_DAYS = 14
    EVIDENCE_DECAY_THRESHOLD = 0.4
    DOCUMENT_OUTDATED_DAYS = 30
    QUALITY_REGRESSION_PCT = 15.0
    MAX_ACTIVE_ALERTS_PER_TYPE = 3

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def run_full_scan(self, user_id: str) -> Dict[str, Any]:
        """Execute all detection routines and return a summary.

        This is the main entry point — call from a cron endpoint
        or after major user actions (profile update, document generation).
        """
        results = {
            "user_id": user_id,
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "alerts_created": 0,
            "checks": {},
        }

        checks = [
            ("profile_staleness", self._check_profile_staleness),
            ("evidence_decay", self._check_evidence_decay),
            ("document_freshness", self._check_document_freshness),
            ("quality_regression", self._check_quality_regression),
            ("interview_prep", self._check_interview_prep),
            ("opportunity_match", self._check_opportunity_match),
        ]

        for check_name, check_fn in checks:
            try:
                count = await check_fn(user_id)
                results["checks"][check_name] = {"alerts": count, "status": "ok"}
                results["alerts_created"] += count
            except Exception as e:
                logger.warning(
                    "career_monitor.check_failed",
                    check=check_name,
                    user_id=user_id,
                    error=str(e)[:200],
                )
                results["checks"][check_name] = {"alerts": 0, "status": "error", "error": str(e)[:100]}

        logger.info(
            "career_monitor.scan_complete",
            user_id=user_id,
            total_alerts=results["alerts_created"],
        )
        return results

    # ── Detection routines ────────────────────────────────────────────

    async def _check_profile_staleness(self, user_id: str) -> int:
        """Alert if profile hasn't been updated recently."""
        profiles = await self.db.query(
            TABLES["profiles"],
            filters=[("user_id", "==", user_id)],
            limit=1,
        )
        if not profiles:
            return 0

        profile = profiles[0]
        updated_at = profile.get("updated_at") or profile.get("created_at")
        if not updated_at:
            return 0

        if isinstance(updated_at, str):
            try:
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return 0

        days_stale = (datetime.now(timezone.utc) - updated_at).days
        if days_stale >= self.PROFILE_STALE_DAYS:
            return await self._create_alert_if_not_exists(
                user_id=user_id,
                alert_type="profile_stale",
                severity="warning" if days_stale < 30 else "critical",
                title=f"Profile hasn't been updated in {days_stale} days",
                description=(
                    "Your profile may contain outdated information. "
                    "Updating it ensures your generated documents reflect your latest experience, "
                    "skills, and achievements."
                ),
                action_url="/profile",
                metadata={"days_stale": days_stale, "last_updated": updated_at.isoformat()},
                expires_hours=72,
            )
        return 0

    async def _check_evidence_decay(self, user_id: str) -> int:
        """Alert if canonical evidence confidence is dropping."""
        try:
            nodes = await self.db.query(
                TABLES["user_evidence_nodes"],
                filters=[("user_id", "==", user_id)],
            )
        except Exception:
            return 0

        if not nodes or len(nodes) < 3:
            return 0

        low_confidence = [n for n in nodes if (n.get("confidence") or 0) < self.EVIDENCE_DECAY_THRESHOLD]
        decay_ratio = len(low_confidence) / len(nodes)

        if decay_ratio > 0.3:
            return await self._create_alert_if_not_exists(
                user_id=user_id,
                alert_type="evidence_decay",
                severity="warning" if decay_ratio < 0.5 else "critical",
                title=f"{len(low_confidence)} evidence items have low confidence",
                description=(
                    f"{int(decay_ratio * 100)}% of your evidence nodes have confidence below "
                    f"{self.EVIDENCE_DECAY_THRESHOLD}. Refresh your profile or apply to more "
                    "jobs to rebuild evidence strength."
                ),
                action_url="/evidence",
                metadata={
                    "total_nodes": len(nodes),
                    "low_confidence_count": len(low_confidence),
                    "decay_ratio": round(decay_ratio, 2),
                },
                expires_hours=168,
            )
        return 0

    async def _check_document_freshness(self, user_id: str) -> int:
        """Alert if documents were generated with stale evidence."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.DOCUMENT_OUTDATED_DAYS)).isoformat()

        try:
            old_docs = await self.db.query(
                TABLES["documents"],
                filters=[("user_id", "==", user_id)],
                order_by="created_at",
                order_direction="ASCENDING",
                limit=50,
            )
        except Exception:
            return 0

        outdated = [
            d for d in old_docs
            if d.get("created_at") and d["created_at"] < cutoff
        ]

        if len(outdated) >= 3:
            return await self._create_alert_if_not_exists(
                user_id=user_id,
                alert_type="document_outdated",
                severity="info",
                title=f"{len(outdated)} documents are over {self.DOCUMENT_OUTDATED_DAYS} days old",
                description=(
                    "Older documents may not reflect your latest skills and experience. "
                    "Consider regenerating them for active applications."
                ),
                action_url="/applications",
                metadata={"outdated_count": len(outdated)},
                expires_hours=336,
            )
        return 0

    async def _check_quality_regression(self, user_id: str) -> int:
        """Alert if pipeline quality scores have dropped significantly."""
        try:
            recent_telemetry = await self.db.query(
                TABLES["pipeline_telemetry"],
                filters=[("user_id", "==", user_id)],
                order_by="created_at",
                order_direction="DESCENDING",
                limit=20,
            )
        except Exception:
            return 0

        if len(recent_telemetry) < 5:
            return 0

        # Split into recent (last 5) vs baseline (rest)
        recent_scores = [t.get("quality_score", 0) for t in recent_telemetry[:5] if t.get("quality_score")]
        baseline_scores = [t.get("quality_score", 0) for t in recent_telemetry[5:] if t.get("quality_score")]

        if not recent_scores or not baseline_scores:
            return 0

        recent_avg = sum(recent_scores) / len(recent_scores)
        baseline_avg = sum(baseline_scores) / len(baseline_scores)

        if baseline_avg > 0:
            drop_pct = ((baseline_avg - recent_avg) / baseline_avg) * 100
            if drop_pct >= self.QUALITY_REGRESSION_PCT:
                return await self._create_alert_if_not_exists(
                    user_id=user_id,
                    alert_type="quality_regression",
                    severity="warning" if drop_pct < 25 else "critical",
                    title=f"Pipeline quality dropped {drop_pct:.0f}% recently",
                    description=(
                        f"Your recent document quality scores average {recent_avg:.0f} vs "
                        f"a baseline of {baseline_avg:.0f}. This may indicate profile issues "
                        "or job description complexity changes."
                    ),
                    action_url="/dashboard",
                    metadata={
                        "recent_avg": round(recent_avg, 1),
                        "baseline_avg": round(baseline_avg, 1),
                        "drop_pct": round(drop_pct, 1),
                    },
                    expires_hours=48,
                )
        return 0

    async def _check_interview_prep(self, user_id: str) -> int:
        """Alert if user has upcoming interviews without prep materials."""
        try:
            applications = await self.db.query(
                TABLES["applications"],
                filters=[("user_id", "==", user_id), ("status", "==", "interview")],
                limit=10,
            )
        except Exception:
            return 0

        alerts_created = 0
        for app in applications:
            # Check if interview session exists
            app_id = app.get("id")
            if not app_id:
                continue

            try:
                sessions = await self.db.query(
                    TABLES["interview_sessions"],
                    filters=[("user_id", "==", user_id), ("application_id", "==", app_id)],
                    limit=1,
                )
            except Exception:
                continue

            if not sessions:
                company = app.get("company_name") or app.get("company") or "Unknown"
                title = app.get("job_title") or app.get("title") or "Unknown"
                count = await self._create_alert_if_not_exists(
                    user_id=user_id,
                    alert_type="interview_prep_reminder",
                    severity="warning",
                    title=f"Interview prep needed for {company}",
                    description=(
                        f'You have an upcoming interview for "{title}" at {company} '
                        "but haven't generated interview prep materials yet."
                    ),
                    action_url=f"/applications/{app_id}",
                    metadata={"application_id": app_id, "company": company, "job_title": title},
                    expires_hours=168,
                )
                alerts_created += count
        return alerts_created

    async def _check_opportunity_match(self, user_id: str) -> int:
        """Alert if saved job alerts have strong matches to current profile."""
        try:
            matches = await self.db.query(
                TABLES["job_matches"],
                filters=[("user_id", "==", user_id)],
                order_by="match_score",
                order_direction="DESCENDING",
                limit=5,
            )
        except Exception:
            return 0

        alerts_created = 0
        for match in matches:
            score = match.get("match_score") or match.get("score") or 0
            if score >= 85:
                job_title = match.get("job_title") or match.get("title") or "Role"
                company = match.get("company_name") or match.get("company") or ""
                count = await self._create_alert_if_not_exists(
                    user_id=user_id,
                    alert_type="opportunity_match",
                    severity="info",
                    title=f"Strong match: {job_title}" + (f" at {company}" if company else ""),
                    description=(
                        f"This opportunity has a {score}% match with your profile — "
                        "well above average. Consider applying soon."
                    ),
                    action_url=f"/jobs/{match.get('id', '')}",
                    metadata={"match_score": score, "job_title": job_title, "company": company},
                    expires_hours=336,
                )
                alerts_created += count
        return alerts_created

    # ── Alert CRUD helpers ────────────────────────────────────────────

    async def _create_alert_if_not_exists(
        self,
        user_id: str,
        alert_type: str,
        severity: str,
        title: str,
        description: str,
        action_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_hours: int = 168,
    ) -> int:
        """Create an alert only if a similar active one doesn't already exist.

        Returns 1 if created, 0 if deduplicated.
        """
        # Check for existing active alert of same type
        try:
            existing = await self.db.query(
                TABLES["career_alerts"],
                filters=[
                    ("user_id", "==", user_id),
                    ("alert_type", "==", alert_type),
                ],
                order_by="created_at",
                order_direction="DESCENDING",
                limit=self.MAX_ACTIVE_ALERTS_PER_TYPE + 1,
            )

            # Filter to active (not dismissed)
            active = [a for a in existing if not a.get("dismissed_at")]
            if len(active) >= self.MAX_ACTIVE_ALERTS_PER_TYPE:
                return 0
        except Exception:
            pass  # If we can't check, create anyway

        try:
            await self.db.create(
                TABLES["career_alerts"],
                {
                    "user_id": user_id,
                    "alert_type": alert_type,
                    "severity": severity,
                    "title": title,
                    "description": description,
                    "action_url": action_url,
                    "metadata": metadata or {},
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(hours=expires_hours)
                    ).isoformat(),
                },
            )
            logger.info(
                "career_monitor.alert_created",
                user_id=user_id,
                alert_type=alert_type,
                severity=severity,
            )
            return 1
        except Exception as e:
            logger.warning("career_monitor.alert_create_failed", error=str(e)[:200])
            return 0

    async def get_active_alerts(
        self,
        user_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get active (undismissed, unexpired) alerts for a user."""
        try:
            alerts = await self.db.query(
                TABLES["career_alerts"],
                filters=[("user_id", "==", user_id)],
                order_by="created_at",
                order_direction="DESCENDING",
                limit=limit * 2,  # fetch extra to filter
            )

            now = datetime.now(timezone.utc).isoformat()
            active = []
            for a in alerts:
                if a.get("dismissed_at"):
                    continue
                if a.get("expires_at") and a["expires_at"] < now:
                    continue
                active.append(a)
                if len(active) >= limit:
                    break

            return active
        except Exception as e:
            logger.warning("career_monitor.get_alerts_failed", error=str(e)[:200])
            return []

    async def dismiss_alert(self, user_id: str, alert_id: str) -> bool:
        """Dismiss an alert (soft-delete)."""
        try:
            await self.db.update(
                TABLES["career_alerts"],
                alert_id,
                {"dismissed_at": datetime.now(timezone.utc).isoformat()},
            )
            return True
        except Exception as e:
            logger.warning("career_monitor.dismiss_failed", error=str(e)[:200])
            return False

    async def mark_alert_read(self, user_id: str, alert_id: str) -> bool:
        """Mark an alert as read."""
        try:
            await self.db.update(
                TABLES["career_alerts"],
                alert_id,
                {"read_at": datetime.now(timezone.utc).isoformat()},
            )
            return True
        except Exception as e:
            logger.warning("career_monitor.mark_read_failed", error=str(e)[:200])
            return False

    async def get_alert_summary(self, user_id: str) -> Dict[str, Any]:
        """Get a summary of alert counts by type and severity."""
        alerts = await self.get_active_alerts(user_id, limit=100)

        by_type: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        unread = 0

        for a in alerts:
            t = a.get("alert_type", "unknown")
            s = a.get("severity", "info")
            by_type[t] = by_type.get(t, 0) + 1
            by_severity[s] = by_severity.get(s, 0) + 1
            if not a.get("read_at"):
                unread += 1

        return {
            "total_active": len(alerts),
            "unread": unread,
            "by_type": by_type,
            "by_severity": by_severity,
            "has_critical": by_severity.get("critical", 0) > 0,
        }
