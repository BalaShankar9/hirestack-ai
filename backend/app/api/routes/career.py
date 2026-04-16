"""
Career Analytics routes - Timeline, trends, portfolio, outcomes, telemetry, self-tuning,
predictions, health monitoring, and evidence-graph exposure (Supabase)
"""
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.career_analytics import (
    CareerAnalyticsService,
    PipelineTelemetryService,
    SelfTuningEngine,
    PipelineHealthMonitor,
)
from app.api.deps import get_current_user, validate_uuid
from app.core.security import limiter

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
#  Existing: Timeline / Snapshot / Portfolio
# ═══════════════════════════════════════════════════════════════════════

@router.post("/snapshot")
@limiter.limit("10/minute")
async def capture_snapshot(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Capture a daily career progress snapshot."""
    service = CareerAnalyticsService()
    return await service.capture_snapshot(current_user["id"])


@router.get("/timeline")
@limiter.limit("30/minute")
async def get_timeline(
    request: Request,
    days: int = Query(90, ge=1, le=365),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get career progress timeline."""
    service = CareerAnalyticsService()
    return await service.get_timeline(current_user["id"], days)


@router.get("/portfolio")
@limiter.limit("30/minute")
async def get_portfolio_summary(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get comprehensive career portfolio summary."""
    service = CareerAnalyticsService()
    return await service.get_portfolio_summary(current_user["id"])


# ═══════════════════════════════════════════════════════════════════════
#  Outcome Tracking — closed-loop quality learning
# ═══════════════════════════════════════════════════════════════════════

class OutcomeSignalRequest(BaseModel):
    application_id: str = Field(..., min_length=1, max_length=100)
    signal_type: str = Field(..., pattern=r"^(exported|applied|screened|interview|interview_done|offer|accepted|rejected)$")
    signal_data: Optional[Dict[str, Any]] = None


@router.post("/outcomes")
@limiter.limit("30/minute")
async def record_outcome(
    request: Request,
    body: OutcomeSignalRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Record an outcome signal (exported, applied, interview, offer, etc.)."""
    validate_uuid(body.application_id, "application_id")
    service = CareerAnalyticsService()
    try:
        return await service.record_outcome(
            user_id=current_user["id"],
            application_id=body.application_id,
            signal_type=body.signal_type,
            signal_data=body.signal_data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/outcomes/funnel")
@limiter.limit("30/minute")
async def get_conversion_funnel(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the user's application conversion funnel."""
    service = CareerAnalyticsService()
    return await service.get_conversion_funnel(current_user["id"])


@router.get("/outcomes/effectiveness")
@limiter.limit("30/minute")
async def get_strategy_effectiveness(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Analyze which pipeline strategies produce better outcomes."""
    service = CareerAnalyticsService()
    return await service.get_strategy_effectiveness(current_user["id"])


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Telemetry — cost, token, and quality dashboards
# ═══════════════════════════════════════════════════════════════════════

@router.get("/telemetry/summary")
@limiter.limit("30/minute")
async def get_telemetry_summary(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get aggregated pipeline cost and token summary."""
    service = PipelineTelemetryService()
    return await service.get_user_cost_summary(current_user["id"], days)


@router.get("/telemetry/trend/{pipeline_name}")
@limiter.limit("30/minute")
async def get_telemetry_trend(
    request: Request,
    pipeline_name: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get quality score trend for a specific pipeline."""
    service = PipelineTelemetryService()
    return await service.get_pipeline_quality_trend(
        current_user["id"], pipeline_name, limit,
    )


@router.get("/telemetry/phase-latencies")
@limiter.limit("60/minute")
async def get_phase_latencies(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Return per-phase latency percentiles from the in-process MetricsCollector.

    Data is drawn from the rolling window of the current process (up to 100 runs).
    Resets on server restart. Suitable for live regression visibility in the UI.
    """
    from app.core.metrics import MetricsCollector

    collector = MetricsCollector.get()
    stage_stats = collector.get_stage_stats()

    # Enrich with SLO thresholds from the pipeline runtime
    slo_map: Dict[str, int] = {}
    try:
        from app.services.pipeline_runtime import PHASE_SLO_MS
        slo_map = dict(PHASE_SLO_MS)
    except Exception:
        pass

    enriched: Dict[str, Any] = {}
    for stage_name, stats in stage_stats.items():
        slo_ms = slo_map.get(stage_name)
        enriched[stage_name] = {
            **stats,
            "slo_ms": slo_ms,
            "slo_breached": bool(slo_ms and stats["p95_ms"] > slo_ms),
        }

    return {
        "stages": enriched,
        "slo_map": slo_map,
        "window_size": collector._window_size,
        "pipeline_runs": {
            name: pstats.get("count", 0)
            for name, pstats in collector.get_stats().get("pipelines", {}).items()
        },
    }


# ═══════════════════════════════════════════════════════════════════════
#  Production Replay — reconstruct pipeline state from event log
# ═══════════════════════════════════════════════════════════════════════

@router.get("/replay/{job_id}")
@limiter.limit("10/minute")
async def replay_pipeline_state(
    request: Request,
    job_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Reconstruct full pipeline execution state from the event log.

    Returns the durable workflow state (stages, latencies, artifacts)
    for debugging or replay analysis. Does NOT re-execute anything.
    """
    validate_uuid(job_id, "job_id")
    try:
        from app.core.database import get_supabase, TABLES
        from ai_engine.agents.workflow_runtime import WorkflowEventStore, reconstruct_state

        sb = get_supabase()
        store = WorkflowEventStore(sb, TABLES)
        events = await store.load_events(job_id)
        if not events:
            raise HTTPException(status_code=404, detail="No events found for this job")

        # Verify ownership
        first_event = events[0]
        if first_event.get("user_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")

        state = reconstruct_state(events, job_id)
        return {
            "job_id": job_id,
            "workflow_id": state.workflow_id if state else None,
            "pipeline_name": state.pipeline_name if state else None,
            "status": state.status if state else "unknown",
            "stages": {
                name: {
                    "status": cp.status.value,
                    "latency_ms": cp.latency_ms,
                    "attempt": cp.attempt,
                    "error": cp.error,
                }
                for name, cp in (state.stages if state else {}).items()
            },
            "total_events": len(events),
            "artifacts_available": list((state.artifacts if state else {}).keys()),
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to reconstruct pipeline state")


# ═══════════════════════════════════════════════════════════════════════
#  Self-Tuning Engine — learns optimal config from outcomes
# ═══════════════════════════════════════════════════════════════════════

@router.get("/tuning/recommendation")
@limiter.limit("10/minute")
async def get_tuning_recommendation(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the self-tuning engine's recommended pipeline config.

    Analyzes historical outcomes + telemetry to find the model,
    research depth, and iteration count that produce the best results.
    """
    engine = SelfTuningEngine()
    return await engine.recommend_config(current_user["id"])


@router.get("/predict/{application_id}")
@limiter.limit("20/minute")
async def predict_interview_likelihood(
    request: Request,
    application_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Predict the likelihood of getting an interview for an application.

    Uses historical outcome data + quality scores to estimate probability.
    Returns a 0-100 prediction with confidence level and contributing factors.
    """
    validate_uuid(application_id, "application_id")
    engine = SelfTuningEngine()
    return await engine.predict_interview_likelihood(
        current_user["id"], application_id,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Health Monitor — quality regression & anomaly detection
# ═══════════════════════════════════════════════════════════════════════

@router.get("/telemetry/health")
@limiter.limit("10/minute")
async def get_pipeline_health(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a pipeline health report with regression and anomaly alerts.

    Compares the last 7 days against the 30-day baseline to detect:
    - Quality score regressions (>15% drop)
    - Cost spikes (>50% increase)
    - Latency anomalies (>2x increase)
    - Model instability (frequent cascade failovers)
    """
    monitor = PipelineHealthMonitor()
    return await monitor.get_health_report(current_user["id"])


# ═══════════════════════════════════════════════════════════════════════
#  Evidence Graph — expose canonical nodes + contradictions for frontend
# ═══════════════════════════════════════════════════════════════════════

@router.get("/evidence-graph")
@limiter.limit("10/minute")
async def get_evidence_graph(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the full evidence graph for the current user.

    Returns canonical evidence nodes and detected contradictions,
    along with evidence strength statistics. This powers the
    frontend evidence graph visualization.
    """
    try:
        from app.core.database import get_supabase
        from ai_engine.agents.evidence_graph import EvidenceGraphBuilder

        sb = get_supabase()
        graph = EvidenceGraphBuilder(
            user_id=current_user["id"],
            db=sb,
        )

        stats = graph.compute_evidence_strength()
        score = graph.compute_evidence_strength_score()

        # Load nodes + contradictions
        nodes = graph._load_existing_nodes()
        contradictions = graph._load_existing_contradictions()

        return {
            "strength_score": score,
            "stats": {
                "total_nodes": stats.total_nodes,
                "verbatim_count": stats.verbatim_count,
                "derived_count": stats.derived_count,
                "inferred_count": stats.inferred_count,
                "user_stated_count": stats.user_stated_count,
                "avg_confidence": round(stats.avg_confidence, 2),
                "contradiction_count": stats.contradiction_count,
                "unresolved_contradictions": stats.unresolved_contradictions,
            },
            "nodes": [
                {
                    "id": n.id,
                    "text": n.canonical_text,
                    "tier": n.tier,
                    "source": n.source,
                    "source_field": n.source_field,
                    "confidence": round(n.confidence, 2),
                }
                for n in nodes[:200]  # Cap at 200 nodes for frontend performance
            ],
            "contradictions": [
                {
                    "type": c.contradiction_type.value if hasattr(c.contradiction_type, 'value') else str(c.contradiction_type),
                    "severity": c.severity,
                    "description": c.description,
                    "node_a_id": c.node_a.id if c.node_a else None,
                    "node_b_id": c.node_b.id if c.node_b else None,
                }
                for c in contradictions[:50]  # Cap at 50
            ],
        }
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to load evidence graph")


# ═══════════════════════════════════════════════════════════════════════
#  Autonomous Career Monitor — proactive alerts
# ═══════════════════════════════════════════════════════════════════════

@router.post("/monitor/scan")
@limiter.limit("5/minute")
async def trigger_career_scan(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Trigger a full autonomous career monitor scan.

    Runs all detection routines (profile staleness, evidence decay,
    quality regression, etc.) and creates alerts for anything that
    needs the user's attention.
    """
    from app.services.career_monitor import AutonomousCareerMonitor
    monitor = AutonomousCareerMonitor()
    return await monitor.run_full_scan(current_user["id"])


@router.get("/alerts")
@limiter.limit("30/minute")
async def get_career_alerts(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get active career alerts for the current user."""
    from app.services.career_monitor import AutonomousCareerMonitor
    monitor = AutonomousCareerMonitor()
    return await monitor.get_active_alerts(current_user["id"], limit=limit)


@router.get("/alerts/summary")
@limiter.limit("30/minute")
async def get_alert_summary(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a summary of alert counts by type and severity."""
    from app.services.career_monitor import AutonomousCareerMonitor
    monitor = AutonomousCareerMonitor()
    return await monitor.get_alert_summary(current_user["id"])


@router.post("/alerts/{alert_id}/dismiss")
@limiter.limit("30/minute")
async def dismiss_alert(
    request: Request,
    alert_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Dismiss a career alert."""
    validate_uuid(alert_id, "alert_id")
    from app.services.career_monitor import AutonomousCareerMonitor
    monitor = AutonomousCareerMonitor()
    success = await monitor.dismiss_alert(current_user["id"], alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found or already dismissed")
    return {"status": "dismissed"}


@router.post("/alerts/{alert_id}/read")
@limiter.limit("60/minute")
async def mark_alert_read(
    request: Request,
    alert_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Mark a career alert as read."""
    validate_uuid(alert_id, "alert_id")
    from app.services.career_monitor import AutonomousCareerMonitor
    monitor = AutonomousCareerMonitor()
    success = await monitor.mark_alert_read(current_user["id"], alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "read"}


# ═══════════════════════════════════════════════════════════════════════
#  Document Evolution — semantic diff tracking
# ═══════════════════════════════════════════════════════════════════════

class DocumentEvolutionRequest(BaseModel):
    document_id: str = Field(..., min_length=1, max_length=100)
    old_content: str = Field(..., min_length=1)
    new_content: str = Field(..., min_length=1)
    version_from: int = Field(..., ge=0)
    version_to: int = Field(..., ge=1)
    application_id: Optional[str] = None
    target_keywords: Optional[list] = None


@router.post("/document-evolution")
@limiter.limit("10/minute")
async def analyze_document_evolution(
    request: Request,
    body: DocumentEvolutionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Analyze the semantic evolution between two document versions.

    Returns improvement scores, keyword changes, evidence deltas,
    and structural analysis.
    """
    if body.application_id:
        validate_uuid(body.application_id, "application_id")
    validate_uuid(body.document_id, "document_id")

    from app.services.document_evolution import DocumentEvolutionEngine
    engine = DocumentEvolutionEngine()
    return await engine.analyze_evolution(
        user_id=current_user["id"],
        document_id=body.document_id,
        old_content=body.old_content,
        new_content=body.new_content,
        version_from=body.version_from,
        version_to=body.version_to,
        application_id=body.application_id,
        target_keywords=body.target_keywords,
    )


@router.get("/document-evolution/timeline")
@limiter.limit("30/minute")
async def get_evolution_timeline(
    request: Request,
    document_id: Optional[str] = Query(None),
    application_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the evolution timeline for a document or all documents."""
    from app.services.document_evolution import DocumentEvolutionEngine
    engine = DocumentEvolutionEngine()
    return await engine.get_evolution_timeline(
        user_id=current_user["id"],
        document_id=document_id,
        application_id=application_id,
        limit=limit,
    )


@router.get("/document-evolution/trend")
@limiter.limit("30/minute")
async def get_improvement_trend(
    request: Request,
    limit: int = Query(30, ge=1, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get the overall document improvement trend.

    Shows whether documents are getting better over time.
    """
    from app.services.document_evolution import DocumentEvolutionEngine
    engine = DocumentEvolutionEngine()
    return await engine.get_improvement_trend(current_user["id"], limit=limit)


# ═══════════════════════════════════════════════════════════════════════
#  Predictive Career Forecaster — enhanced predictions
# ═══════════════════════════════════════════════════════════════════════

@router.get("/predict/offer/{application_id}")
@limiter.limit("20/minute")
async def predict_offer_probability(
    request: Request,
    application_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Predict offer probability for an application that has an interview.

    Second stage of prediction: interview secured → what's the offer chance?
    """
    validate_uuid(application_id, "application_id")
    from app.services.career_analytics import PredictiveCareerForecaster
    forecaster = PredictiveCareerForecaster()
    return await forecaster.predict_offer_probability(
        current_user["id"], application_id,
    )


@router.get("/momentum")
@limiter.limit("10/minute")
async def get_career_momentum(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get overall career momentum index.

    Combines application velocity, outcome trend, quality trend,
    evidence growth, and profile freshness into a single score.
    """
    from app.services.career_analytics import PredictiveCareerForecaster
    forecaster = PredictiveCareerForecaster()
    return await forecaster.get_career_momentum(current_user["id"])
