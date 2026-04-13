"""
Career Analytics Service
Timeline snapshots, score trends, industry benchmarking, and outcome tracking (Supabase).

Outcome Tracking Engine:
  Closes the feedback loop from document export → application → interview → offer.
  Every outcome signal is persisted and correlated back to the pipeline run and
  agent configuration that produced the documents. This enables:
    - Measuring which pipeline configurations lead to more interviews
    - Tracking which document variants get better response rates
    - Per-user and aggregate conversion funnels
    - Strategy effectiveness scoring (which research depth, tone, format works best)
"""
from typing import Optional, Dict, Any, List
from datetime import date, datetime, timezone
import structlog

from app.core.database import get_db, TABLES, SupabaseDB

logger = structlog.get_logger()


class CareerAnalyticsService:
    """Service for career progress tracking and analytics."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def capture_snapshot(self, user_id: str) -> Dict[str, Any]:
        """Capture a daily career progress snapshot."""
        today = date.today().isoformat()

        # Check if snapshot exists for today
        existing = await self.db.query(
            TABLES["career_snapshots"],
            filters=[("user_id", "==", user_id), ("snapshot_date", "==", today)],
            limit=1,
        )
        if existing:
            return existing[0]

        # Gather current scores
        gap_reports = await self.db.query(
            TABLES["gap_reports"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=5,
        )

        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
        )

        interviews = await self.db.query(
            TABLES["interview_sessions"],
            filters=[("user_id", "==", user_id), ("status", "==", "completed")],
        )

        ats_scans = await self.db.query(
            TABLES["ats_scans"],
            filters=[("user_id", "==", user_id)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=10,
        )

        # Compute averages
        overall_scores = [r.get("compatibility_score", 0) for r in gap_reports if r.get("compatibility_score")]
        tech_scores = [r.get("skill_score", 0) for r in gap_reports if r.get("skill_score")]
        exp_scores = [r.get("experience_score", 0) for r in gap_reports if r.get("experience_score")]
        edu_scores = [r.get("education_score", 0) for r in gap_reports if r.get("education_score")]
        ats_scores_list = [s.get("ats_score", 0) for s in ats_scans if s.get("ats_score")]

        record = {
            "user_id": user_id,
            "snapshot_date": today,
            "overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else None,
            "technical_score": sum(tech_scores) / len(tech_scores) if tech_scores else None,
            "experience_score": sum(exp_scores) / len(exp_scores) if exp_scores else None,
            "education_score": sum(edu_scores) / len(edu_scores) if edu_scores else None,
            "applications_count": len(applications),
            "interviews_completed": len(interviews),
            "avg_ats_score": sum(ats_scores_list) / len(ats_scores_list) if ats_scores_list else None,
            "metadata": {
                "gap_reports_count": len(gap_reports),
                "ats_scans_count": len(ats_scans),
            },
        }

        doc_id = await self.db.create(TABLES["career_snapshots"], record)
        logger.info("career_snapshot_captured", snapshot_id=doc_id)
        return await self.db.get(TABLES["career_snapshots"], doc_id)

    async def get_timeline(self, user_id: str, days: int = 90) -> List[Dict[str, Any]]:
        """Get career progress timeline."""
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        return await self.db.query(
            TABLES["career_snapshots"],
            filters=[("user_id", "==", user_id), ("snapshot_date", ">=", cutoff)],
            order_by="snapshot_date",
        )

    async def get_portfolio_summary(self, user_id: str) -> Dict[str, Any]:
        """Generate a comprehensive career portfolio summary."""
        applications = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id)],
        )
        interviews = await self.db.query(
            TABLES["interview_sessions"],
            filters=[("user_id", "==", user_id), ("status", "==", "completed")],
        )
        evidence = await self.db.query(
            TABLES["evidence"],
            filters=[("user_id", "==", user_id)],
        )
        streaks = await self.db.query(
            TABLES["learning_streaks"],
            filters=[("user_id", "==", user_id)],
            limit=1,
        )

        timeline = await self.get_timeline(user_id, days=90)

        # Compute score trends
        if len(timeline) >= 2:
            first = timeline[0].get("overall_score") or 0
            last = timeline[-1].get("overall_score") or 0
            trend = last - first
        else:
            trend = 0

        return {
            "total_applications": len(applications),
            "total_interviews": len(interviews),
            "total_evidence": len(evidence),
            "avg_interview_score": (
                sum(i.get("overall_score", 0) or 0 for i in interviews) / len(interviews)
                if interviews else 0
            ),
            "learning_streak": streaks[0] if streaks else None,
            "score_trend": trend,
            "timeline": timeline[-30:],  # last 30 data points
        }

    # ═══════════════════════════════════════════════════════════════════
    #  Outcome Tracking Engine — closed-loop quality learning
    # ═══════════════════════════════════════════════════════════════════

    async def record_outcome(
        self,
        user_id: str,
        application_id: str,
        signal_type: str,
        signal_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record an outcome signal for a specific application.

        Signal types (progressive funnel):
          - exported:       User exported document(s) — intent to apply
          - applied:        User confirmed they submitted the application
          - screened:       Application passed initial screening
          - interview:      User got an interview
          - interview_done: Interview completed (with optional self-score)
          - offer:          User received an offer
          - accepted:       User accepted the offer
          - rejected:       Application was rejected (at any stage)

        Each signal is correlated back to the generation job so we can
        measure which pipeline configurations produce better outcomes.
        """
        valid_signals = {
            "exported", "applied", "screened", "interview",
            "interview_done", "offer", "accepted", "rejected",
        }
        if signal_type not in valid_signals:
            raise ValueError(f"Invalid signal_type: {signal_type}. Must be one of {valid_signals}")

        # Look up the application to find the generation job that produced it
        app = await self.db.get(TABLES["applications"], application_id)
        if not app or app.get("user_id") != user_id:
            raise ValueError("Application not found or access denied")

        job_id = app.get("generation_job_id") or app.get("job_id")

        # Look up pipeline telemetry for this job (if available)
        pipeline_config: Dict[str, Any] = {}
        if job_id:
            telemetry = await self.db.query(
                TABLES["pipeline_telemetry"],
                filters=[("job_id", "==", job_id)],
                limit=1,
            )
            if telemetry:
                pipeline_config = {
                    "pipeline_name": telemetry[0].get("pipeline_name"),
                    "model_used": telemetry[0].get("model_used"),
                    "research_depth": telemetry[0].get("research_depth"),
                    "iterations_used": telemetry[0].get("iterations_used"),
                    "quality_scores": telemetry[0].get("quality_scores"),
                }

        record = {
            "user_id": user_id,
            "application_id": application_id,
            "generation_job_id": job_id,
            "signal_type": signal_type,
            "signal_data": signal_data or {},
            "pipeline_config": pipeline_config,
        }

        doc_id = await self.db.create(TABLES["outcome_signals"], record)
        logger.info(
            "outcome_signal_recorded",
            signal_type=signal_type,
            application_id=application_id,
            job_id=job_id,
        )
        return {"id": doc_id, **record}

    async def get_conversion_funnel(self, user_id: str) -> Dict[str, Any]:
        """Get the user's application conversion funnel.

        Returns counts at each stage of the pipeline:
        exported → applied → screened → interview → offer → accepted
        """
        signals = await self.db.query(
            TABLES["outcome_signals"],
            filters=[("user_id", "==", user_id)],
        )

        # Count unique applications at each stage
        stages = ["exported", "applied", "screened", "interview", "interview_done", "offer", "accepted", "rejected"]
        funnel: Dict[str, set] = {s: set() for s in stages}

        for sig in signals:
            st = sig.get("signal_type", "")
            app_id = sig.get("application_id", "")
            if st in funnel and app_id:
                funnel[st].add(app_id)

        counts = {s: len(ids) for s, ids in funnel.items()}

        # Compute conversion rates
        rates: Dict[str, float] = {}
        pairs = [
            ("exported", "applied"),
            ("applied", "screened"),
            ("screened", "interview"),
            ("interview", "offer"),
            ("offer", "accepted"),
        ]
        for from_stage, to_stage in pairs:
            from_count = counts.get(from_stage, 0)
            to_count = counts.get(to_stage, 0)
            rates[f"{from_stage}_to_{to_stage}"] = (
                round(to_count / from_count * 100, 1) if from_count > 0 else 0.0
            )

        return {
            "funnel": counts,
            "conversion_rates": rates,
            "total_signals": len(signals),
        }

    async def get_strategy_effectiveness(self, user_id: str) -> Dict[str, Any]:
        """Analyze which pipeline strategies produce better outcomes.

        Groups outcomes by pipeline configuration (model, research depth,
        iterations) and computes interview/offer rates per strategy.
        """
        signals = await self.db.query(
            TABLES["outcome_signals"],
            filters=[("user_id", "==", user_id)],
        )

        # Group by pipeline config dimension
        by_model: Dict[str, Dict[str, int]] = {}
        by_depth: Dict[str, Dict[str, int]] = {}

        for sig in signals:
            config = sig.get("pipeline_config") or {}
            model = config.get("model_used") or "unknown"
            depth = config.get("research_depth") or "unknown"
            signal_type = sig.get("signal_type", "")

            for group, key in [(by_model, model), (by_depth, depth)]:
                if key not in group:
                    group[key] = {}
                group[key][signal_type] = group[key].get(signal_type, 0) + 1

        def _effectiveness_score(counts: Dict[str, int]) -> float:
            """Score a strategy: interviews are worth 3x, offers 10x."""
            exported = counts.get("exported", 0) or 1
            interviews = counts.get("interview", 0)
            offers = counts.get("offer", 0)
            return round((interviews * 3 + offers * 10) / exported, 2)

        return {
            "by_model": {k: {**v, "_score": _effectiveness_score(v)} for k, v in by_model.items()},
            "by_research_depth": {k: {**v, "_score": _effectiveness_score(v)} for k, v in by_depth.items()},
        }


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Telemetry — per-run cost, token, and quality tracking
# ═══════════════════════════════════════════════════════════════════════

class PipelineTelemetryService:
    """Persists per-pipeline-run cost and quality metrics.

    Captures:
      - Token usage (prompt + completion) and estimated USD cost
      - Model used and cascade failover events
      - Stage-level latencies
      - Quality scores from critic, ATS, readability
      - Pipeline configuration (research depth, iterations, policy)

    This data feeds the Outcome Tracking Engine (which strategies produce
    better results) and the adaptive planner (which thresholds to adjust).
    """

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def record_telemetry(
        self,
        user_id: str,
        job_id: str,
        pipeline_name: str,
        *,
        model_used: str = "",
        research_depth: str = "",
        iterations_used: int = 0,
        total_latency_ms: int = 0,
        stage_latencies: Optional[Dict[str, int]] = None,
        token_usage: Optional[Dict[str, int]] = None,
        quality_scores: Optional[Dict[str, float]] = None,
        evidence_stats: Optional[Dict[str, Any]] = None,
        cost_usd_cents: int = 0,
        cascade_failovers: int = 0,
        pipeline_config: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Persist a telemetry record for a completed pipeline run."""
        record = {
            "user_id": user_id,
            "job_id": job_id,
            "pipeline_name": pipeline_name,
            "model_used": model_used,
            "research_depth": research_depth,
            "iterations_used": iterations_used,
            "total_latency_ms": total_latency_ms,
            "stage_latencies": stage_latencies or {},
            "token_usage": token_usage or {},
            "quality_scores": quality_scores or {},
            "evidence_stats": evidence_stats or {},
            "cost_usd_cents": cost_usd_cents,
            "cascade_failovers": cascade_failovers,
            "pipeline_config": pipeline_config or {},
        }
        doc_id = await self.db.create(TABLES["pipeline_telemetry"], record)
        logger.info(
            "pipeline_telemetry_recorded",
            pipeline=pipeline_name,
            cost_cents=cost_usd_cents,
            latency_ms=total_latency_ms,
            tokens=token_usage.get("total_tokens", 0) if token_usage else 0,
        )
        return doc_id

    async def get_user_cost_summary(
        self, user_id: str, days: int = 30,
    ) -> Dict[str, Any]:
        """Get aggregated cost summary for a user over the last N days."""
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        records = await self.db.query(
            TABLES["pipeline_telemetry"],
            filters=[("user_id", "==", user_id), ("created_at", ">=", cutoff)],
        )

        total_cost = sum(r.get("cost_usd_cents", 0) for r in records)
        total_tokens = sum(
            (r.get("token_usage") or {}).get("total_tokens", 0) for r in records
        )
        by_pipeline: Dict[str, Dict[str, Any]] = {}
        for r in records:
            name = r.get("pipeline_name", "unknown")
            if name not in by_pipeline:
                by_pipeline[name] = {"count": 0, "cost_cents": 0, "tokens": 0, "avg_latency_ms": 0, "total_latency": 0}
            by_pipeline[name]["count"] += 1
            by_pipeline[name]["cost_cents"] += r.get("cost_usd_cents", 0)
            by_pipeline[name]["tokens"] += (r.get("token_usage") or {}).get("total_tokens", 0)
            by_pipeline[name]["total_latency"] += r.get("total_latency_ms", 0)

        for name, stats in by_pipeline.items():
            if stats["count"] > 0:
                stats["avg_latency_ms"] = stats["total_latency"] // stats["count"]
            del stats["total_latency"]

        return {
            "period_days": days,
            "total_runs": len(records),
            "total_cost_usd_cents": total_cost,
            "total_tokens": total_tokens,
            "by_pipeline": by_pipeline,
        }

    async def get_pipeline_quality_trend(
        self, user_id: str, pipeline_name: str, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get quality score trend for a specific pipeline."""
        records = await self.db.query(
            TABLES["pipeline_telemetry"],
            filters=[("user_id", "==", user_id), ("pipeline_name", "==", pipeline_name)],
            order_by="created_at",
            order_direction="DESCENDING",
            limit=limit,
        )
        return [
            {
                "id": r.get("id"),
                "created_at": r.get("created_at"),
                "quality_scores": r.get("quality_scores"),
                "cost_usd_cents": r.get("cost_usd_cents"),
                "latency_ms": r.get("total_latency_ms"),
                "iterations": r.get("iterations_used"),
            }
            for r in reversed(records)
        ]


# ═══════════════════════════════════════════════════════════════════════
#  Self-Tuning Engine — learns optimal pipeline config from outcomes
# ═══════════════════════════════════════════════════════════════════════

class SelfTuningEngine:
    """Analyzes outcome signals + telemetry to recommend optimal pipeline config.

    Learns which combinations of (model, research_depth, iterations) produce
    the best real-world outcomes (interviews, offers) — not just quality scores.
    This is the closed-loop that makes the system self-improving.

    Usage:
        engine = SelfTuningEngine()
        recommendation = await engine.recommend_config(user_id)
        # → {"model": "gemini-2.5-pro", "research_depth": "thorough", "max_iterations": 2, ...}
    """

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def recommend_config(self, user_id: str) -> Dict[str, Any]:
        """Analyze past runs + outcomes to recommend optimal pipeline config.

        Returns a recommendation dict with confidence level.
        """
        # Gather outcome signals
        signals = await self.db.query(
            TABLES["outcome_signals"],
            filters=[("user_id", "==", user_id)],
        )
        # Gather telemetry
        telemetry = await self.db.query(
            TABLES["pipeline_telemetry"],
            filters=[("user_id", "==", user_id)],
        )

        if len(signals) < 3 or len(telemetry) < 3:
            return {
                "recommendation": "default",
                "confidence": "low",
                "reason": "Not enough data — need at least 3 completed runs with outcomes",
                "config": {},
            }

        # Build a scoring map: config_fingerprint → outcome_score
        config_scores: Dict[str, List[float]] = {}
        config_details: Dict[str, Dict[str, Any]] = {}

        for sig in signals:
            config = sig.get("pipeline_config") or {}
            if not config.get("model_used"):
                continue

            fingerprint = f"{config.get('model_used', '')}|{config.get('research_depth', '')}|{config.get('iterations_used', 0)}"
            signal_type = sig.get("signal_type", "")

            # Weight signals by how far in the funnel they got
            weight_map = {
                "exported": 1, "applied": 2, "screened": 4,
                "interview": 8, "interview_done": 10, "offer": 20,
                "accepted": 25, "rejected": -2,
            }
            score = weight_map.get(signal_type, 0)

            if fingerprint not in config_scores:
                config_scores[fingerprint] = []
                config_details[fingerprint] = config
            config_scores[fingerprint].append(score)

        if not config_scores:
            return {
                "recommendation": "default",
                "confidence": "low",
                "reason": "No outcome signals linked to pipeline configs yet",
                "config": {},
            }

        # Rank configs by average outcome score
        ranked = sorted(
            config_scores.items(),
            key=lambda kv: sum(kv[1]) / len(kv[1]),
            reverse=True,
        )
        best_fingerprint, best_scores = ranked[0]
        best_config = config_details[best_fingerprint]
        avg_score = sum(best_scores) / len(best_scores)

        # Also find the cost-efficiency winner
        cost_efficiency: Dict[str, float] = {}
        for tel in telemetry:
            fp = f"{tel.get('model_used', '')}|{tel.get('research_depth', '')}|{tel.get('iterations_used', 0)}"
            cost = tel.get("cost_usd_cents", 0) or 1
            quality = sum((tel.get("quality_scores") or {}).values()) / max(len((tel.get("quality_scores") or {})), 1)
            if fp not in cost_efficiency:
                cost_efficiency[fp] = 0
            cost_efficiency[fp] += quality / cost

        confidence = "high" if len(best_scores) >= 5 else "medium" if len(best_scores) >= 3 else "low"

        return {
            "recommendation": "tuned",
            "confidence": confidence,
            "reason": f"Based on {len(signals)} outcome signals across {len(config_scores)} configurations",
            "config": {
                "model": best_config.get("model_used", ""),
                "research_depth": best_config.get("research_depth", ""),
                "max_iterations": best_config.get("iterations_used", 2),
            },
            "stats": {
                "avg_outcome_score": round(avg_score, 2),
                "sample_size": len(best_scores),
                "configs_evaluated": len(config_scores),
            },
        }

    async def predict_interview_likelihood(
        self, user_id: str, application_id: str,
    ) -> Dict[str, Any]:
        """Predict interview likelihood for an application based on historical patterns.

        Uses the user's historical outcome data + quality scores to estimate
        the probability of getting an interview. This is a lightweight
        statistical model, not ML — it works with small datasets.
        """
        # Get this application's quality data
        from app.core.database import TABLES
        app = await self.db.get(TABLES["applications"], application_id)
        if not app:
            return {"prediction": 0, "confidence": "none", "factors": []}

        job_id = app.get("generation_job_id") or app.get("job_id")
        app_quality: Dict[str, float] = {}
        if job_id:
            tel = await self.db.query(
                TABLES["pipeline_telemetry"],
                filters=[("job_id", "==", job_id)],
                limit=1,
            )
            if tel:
                app_quality = tel[0].get("quality_scores", {})

        # Get historical outcomes for this user
        signals = await self.db.query(
            TABLES["outcome_signals"],
            filters=[("user_id", "==", user_id)],
        )

        if len(signals) < 5:
            # Not enough data for prediction — use quality scores as proxy
            avg_quality = sum(app_quality.values()) / max(len(app_quality), 1)
            base_prediction = min(100, max(0, int(avg_quality * 0.8)))
            return {
                "prediction": base_prediction,
                "confidence": "low",
                "factors": ["Based on quality scores only — record more outcomes for better predictions"],
            }

        # Calculate base rates
        apps_with_interviews = {s.get("application_id") for s in signals if s.get("signal_type") == "interview"}
        apps_exported = {s.get("application_id") for s in signals if s.get("signal_type") == "exported"}
        base_interview_rate = len(apps_with_interviews) / max(len(apps_exported), 1)

        # Quality score adjustment: compare this app's quality to the average of successful ones
        successful_configs = [
            s.get("pipeline_config", {}).get("quality_scores", {})
            for s in signals if s.get("signal_type") in ("interview", "offer")
        ]

        factors = []
        adjustment = 0.0

        # Factor 1: Quality scores vs successful average
        if app_quality and successful_configs:
            app_avg = sum(app_quality.values()) / max(len(app_quality), 1)
            success_avgs = [
                sum(c.values()) / max(len(c), 1) for c in successful_configs if c
            ]
            if success_avgs:
                success_avg = sum(success_avgs) / len(success_avgs)
                if app_avg >= success_avg:
                    adjustment += 0.15
                    factors.append(f"Quality scores above successful average ({app_avg:.0f} vs {success_avg:.0f})")
                else:
                    adjustment -= 0.10
                    factors.append(f"Quality scores below successful average ({app_avg:.0f} vs {success_avg:.0f})")

        # Factor 2: Model used — do some models correlate with better outcomes?
        if job_id:
            tel = await self.db.query(
                TABLES["pipeline_telemetry"],
                filters=[("job_id", "==", job_id)],
                limit=1,
            )
            if tel:
                model = tel[0].get("model_used", "")
                model_outcomes = [
                    s for s in signals
                    if (s.get("pipeline_config") or {}).get("model_used") == model
                ]
                model_interviews = sum(1 for s in model_outcomes if s.get("signal_type") == "interview")
                model_total = max(sum(1 for s in model_outcomes if s.get("signal_type") == "exported"), 1)
                model_rate = model_interviews / model_total
                if model_rate > base_interview_rate:
                    adjustment += 0.10
                    factors.append(f"Model '{model}' has above-average interview rate ({model_rate:.0%})")

        # Factor 3: Evidence strength
        scores = app.get("scores") or {}
        match_score = scores.get("match", 0)
        if match_score >= 80:
            adjustment += 0.10
            factors.append(f"High match score ({match_score})")
        elif match_score < 50:
            adjustment -= 0.10
            factors.append(f"Low match score ({match_score})")

        prediction = min(100, max(0, int((base_interview_rate + adjustment) * 100)))

        return {
            "prediction": prediction,
            "confidence": "high" if len(signals) >= 15 else "medium",
            "base_interview_rate": round(base_interview_rate * 100, 1),
            "factors": factors,
            "data_points": len(signals),
        }


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Health Monitor — quality regression + anomaly detection
# ═══════════════════════════════════════════════════════════════════════

class PipelineHealthMonitor:
    """Monitors pipeline quality and cost for regressions and anomalies.

    Compares recent runs against historical baselines to detect:
    - Quality regressions (scores dropping)
    - Cost spikes (unexpected token/cost increases)
    - Latency anomalies (pipeline taking much longer)
    - Model health issues (cascade failovers increasing)
    """

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def get_health_report(self, user_id: str) -> Dict[str, Any]:
        """Generate a comprehensive pipeline health report."""
        from datetime import timedelta

        recent_cutoff = (date.today() - timedelta(days=7)).isoformat()
        baseline_cutoff = (date.today() - timedelta(days=30)).isoformat()

        recent = await self.db.query(
            TABLES["pipeline_telemetry"],
            filters=[("user_id", "==", user_id), ("created_at", ">=", recent_cutoff)],
        )
        baseline = await self.db.query(
            TABLES["pipeline_telemetry"],
            filters=[
                ("user_id", "==", user_id),
                ("created_at", ">=", baseline_cutoff),
                ("created_at", "<", recent_cutoff),
            ],
        )

        alerts: List[Dict[str, Any]] = []

        # Quality regression detection
        if recent and baseline:
            recent_avg_quality = self._avg_quality(recent)
            baseline_avg_quality = self._avg_quality(baseline)
            if baseline_avg_quality > 0 and recent_avg_quality < baseline_avg_quality * 0.85:
                alerts.append({
                    "type": "quality_regression",
                    "severity": "high",
                    "message": f"Quality dropped {((1 - recent_avg_quality / baseline_avg_quality) * 100):.0f}% vs 30-day baseline",
                    "recent": round(recent_avg_quality, 1),
                    "baseline": round(baseline_avg_quality, 1),
                })

        # Cost spike detection
        if recent and baseline:
            recent_avg_cost = sum(r.get("cost_usd_cents", 0) for r in recent) / max(len(recent), 1)
            baseline_avg_cost = sum(r.get("cost_usd_cents", 0) for r in baseline) / max(len(baseline), 1)
            if baseline_avg_cost > 0 and recent_avg_cost > baseline_avg_cost * 1.5:
                alerts.append({
                    "type": "cost_spike",
                    "severity": "medium",
                    "message": f"Avg cost increased {((recent_avg_cost / baseline_avg_cost - 1) * 100):.0f}% vs baseline",
                    "recent_cents": round(recent_avg_cost, 1),
                    "baseline_cents": round(baseline_avg_cost, 1),
                })

        # Latency anomaly detection
        if recent and baseline:
            recent_avg_lat = sum(r.get("total_latency_ms", 0) for r in recent) / max(len(recent), 1)
            baseline_avg_lat = sum(r.get("total_latency_ms", 0) for r in baseline) / max(len(baseline), 1)
            if baseline_avg_lat > 0 and recent_avg_lat > baseline_avg_lat * 2:
                alerts.append({
                    "type": "latency_anomaly",
                    "severity": "medium",
                    "message": f"Avg latency doubled ({recent_avg_lat / 1000:.1f}s vs {baseline_avg_lat / 1000:.1f}s baseline)",
                })

        # Cascade failover frequency
        recent_failovers = sum(r.get("cascade_failovers", 0) for r in recent)
        if recent_failovers > 3:
            alerts.append({
                "type": "model_instability",
                "severity": "high",
                "message": f"{recent_failovers} cascade failovers in the last 7 days — model may be degraded",
            })

        # Overall health score
        health_score = 100
        for alert in alerts:
            if alert["severity"] == "high":
                health_score -= 25
            elif alert["severity"] == "medium":
                health_score -= 10
        health_score = max(0, health_score)

        return {
            "health_score": health_score,
            "status": "healthy" if health_score >= 80 else "degraded" if health_score >= 50 else "unhealthy",
            "alerts": alerts,
            "recent_runs": len(recent),
            "baseline_runs": len(baseline),
        }

    def _avg_quality(self, records: List[Dict[str, Any]]) -> float:
        """Compute average quality score across records."""
        scores = []
        for r in records:
            qs = r.get("quality_scores") or {}
            if qs:
                avg = sum(qs.values()) / len(qs)
                scores.append(avg)
        return sum(scores) / max(len(scores), 1)


# ═══════════════════════════════════════════════════════════════════════
#  Predictive Career Forecaster — enhanced probability engine
# ═══════════════════════════════════════════════════════════════════════

class PredictiveCareerForecaster:
    """Advanced prediction engine that goes beyond interview likelihood.

    Provides:
      - Offer probability (interview → offer conversion)
      - Application velocity scoring (how fast user moves through funnel)
      - Strength/weakness decomposition per application
      - Portfolio-level career momentum index
    """

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def predict_offer_probability(
        self, user_id: str, application_id: str,
    ) -> Dict[str, Any]:
        """Predict offer probability given an interview has been secured.

        This is the second stage of the prediction pipeline:
        interview_likelihood → got_interview → offer_probability
        """
        app = await self.db.get(TABLES["applications"], application_id)
        if not app:
            return {"prediction": 0, "confidence": "none", "factors": []}

        signals = await self.db.query(
            TABLES["outcome_signals"],
            filters=[("user_id", "==", user_id)],
        )

        if len(signals) < 5:
            return {
                "prediction": 30,
                "confidence": "low",
                "factors": ["Insufficient outcome data — using industry baseline (30%)"],
            }

        # Interview → offer conversion
        interviews = {s.get("application_id") for s in signals if s.get("signal_type") == "interview"}
        offers = {s.get("application_id") for s in signals if s.get("signal_type") == "offer"}
        base_offer_rate = len(offers & interviews) / max(len(interviews), 1)

        factors = []
        adjustment = 0.0

        # Factor 1: Match score impact on offer
        scores = app.get("scores") or {}
        match_score = scores.get("match", 0)
        if match_score >= 85:
            adjustment += 0.15
            factors.append(f"Excellent match score ({match_score}%) — strong fit signal")
        elif match_score >= 70:
            adjustment += 0.05
            factors.append(f"Good match score ({match_score}%)")
        elif match_score < 50:
            adjustment -= 0.15
            factors.append(f"Low match ({match_score}%) — may struggle in interviews")

        # Factor 2: ATS score correlation with offers
        ats_score = scores.get("ats", 0)
        if ats_score >= 90:
            adjustment += 0.10
            factors.append(f"Strong ATS score ({ats_score}) — resume well-optimized")

        # Factor 3: Evidence strength for the application
        evidence_score = scores.get("evidence", 0) or scores.get("proof", 0)
        if evidence_score >= 80:
            adjustment += 0.10
            factors.append(f"Strong evidence backing ({evidence_score}%) — claims well-supported")
        elif evidence_score < 40:
            adjustment -= 0.10
            factors.append(f"Weak evidence ({evidence_score}%) — claims may not hold up in interviews")

        # Factor 4: How quickly user moves through funnel (velocity)
        app_signals = [s for s in signals if s.get("application_id") == application_id]
        if len(app_signals) >= 2:
            timestamps = sorted(s.get("created_at", "") for s in app_signals)
            if timestamps[0] and timestamps[-1]:
                try:
                    first = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
                    last = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
                    days_in_funnel = (last - first).days
                    if days_in_funnel <= 7:
                        adjustment += 0.05
                        factors.append("Fast funnel progression — strong momentum")
                    elif days_in_funnel > 30:
                        adjustment -= 0.05
                        factors.append("Slow funnel progression — may indicate hesitation")
                except (ValueError, TypeError):
                    pass

        prediction = min(100, max(0, int((base_offer_rate + adjustment) * 100)))

        return {
            "prediction": prediction,
            "confidence": "high" if len(signals) >= 15 else "medium",
            "base_offer_rate": round(base_offer_rate * 100, 1),
            "factors": factors,
            "data_points": len(signals),
        }

    async def get_career_momentum(self, user_id: str) -> Dict[str, Any]:
        """Calculate an overall career momentum index.

        Combines: application volume trend, quality trend, outcome trend,
        evidence growth, and profile activity into a single momentum score.
        """
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        recent_cutoff = (now - timedelta(days=14)).isoformat()
        older_cutoff = (now - timedelta(days=30)).isoformat()

        # Recent vs older applications
        recent_apps = await self.db.query(
            TABLES["applications"],
            filters=[("user_id", "==", user_id), ("created_at", ">=", recent_cutoff)],
        )
        older_apps = await self.db.query(
            TABLES["applications"],
            filters=[
                ("user_id", "==", user_id),
                ("created_at", ">=", older_cutoff),
                ("created_at", "<", recent_cutoff),
            ],
        )

        # Recent vs older outcomes
        recent_signals = await self.db.query(
            TABLES["outcome_signals"],
            filters=[("user_id", "==", user_id), ("created_at", ">=", recent_cutoff)],
        )
        older_signals = await self.db.query(
            TABLES["outcome_signals"],
            filters=[
                ("user_id", "==", user_id),
                ("created_at", ">=", older_cutoff),
                ("created_at", "<", recent_cutoff),
            ],
        )

        # Score components (each 0-20, total 0-100)
        components: Dict[str, float] = {}

        # Application velocity (0-20)
        app_velocity = len(recent_apps) - len(older_apps)
        components["application_velocity"] = max(0, min(20, 10 + app_velocity * 2))

        # Outcome momentum (0-20)
        recent_positive = sum(1 for s in recent_signals if s.get("signal_type") in ("interview", "offer", "accepted"))
        older_positive = sum(1 for s in older_signals if s.get("signal_type") in ("interview", "offer", "accepted"))
        components["outcome_momentum"] = max(0, min(20, 10 + (recent_positive - older_positive) * 5))

        # Quality trend (0-20) — from telemetry
        try:
            telemetry = await self.db.query(
                TABLES["pipeline_telemetry"],
                filters=[("user_id", "==", user_id)],
                order_by="created_at",
                order_direction="DESCENDING",
                limit=10,
            )
            if len(telemetry) >= 4:
                recent_q = [
                    sum((t.get("quality_scores") or {}).values()) / max(len((t.get("quality_scores") or {})), 1)
                    for t in telemetry[:5]
                ]
                older_q = [
                    sum((t.get("quality_scores") or {}).values()) / max(len((t.get("quality_scores") or {})), 1)
                    for t in telemetry[5:]
                ]
                avg_recent = sum(recent_q) / len(recent_q)
                avg_older = sum(older_q) / len(older_q) if older_q else avg_recent
                quality_delta = avg_recent - avg_older
                components["quality_trend"] = max(0, min(20, 10 + quality_delta * 0.5))
            else:
                components["quality_trend"] = 10
        except Exception:
            components["quality_trend"] = 10

        # Evidence growth (0-20) — count evidence nodes
        try:
            evidence = await self.db.query(
                TABLES["user_evidence_nodes"],
                filters=[("user_id", "==", user_id)],
            )
            evidence_count = len(evidence)
            # 20+ evidence nodes = full score
            components["evidence_strength"] = max(0, min(20, evidence_count))
        except Exception:
            components["evidence_strength"] = 10

        # Profile freshness (0-20)
        try:
            profiles = await self.db.query(
                TABLES["profiles"],
                filters=[("user_id", "==", user_id)],
                limit=1,
            )
            if profiles:
                updated = profiles[0].get("updated_at") or profiles[0].get("created_at", "")
                if updated:
                    try:
                        updated_dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
                        days_since = (now - updated_dt).days
                        # Updated within 7 days = 20, 14 days = 15, 30+ days = 5
                        components["profile_freshness"] = max(5, min(20, 20 - days_since))
                    except (ValueError, TypeError):
                        components["profile_freshness"] = 10
                else:
                    components["profile_freshness"] = 10
            else:
                components["profile_freshness"] = 0
        except Exception:
            components["profile_freshness"] = 10

        total = sum(components.values())

        if total >= 80:
            trend = "accelerating"
        elif total >= 60:
            trend = "steady"
        elif total >= 40:
            trend = "decelerating"
        else:
            trend = "stalled"

        return {
            "momentum_score": round(total),
            "trend": trend,
            "components": {k: round(v, 1) for k, v in components.items()},
            "recent_applications": len(recent_apps),
            "recent_positive_outcomes": recent_positive,
        }
