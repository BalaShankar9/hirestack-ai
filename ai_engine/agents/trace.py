"""
Agent pipeline tracing and observability.

Records each agent stage's timing, status, and output summary.
Persists to the agent_traces table for debugging and quality monitoring.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.trace")


class AgentTracer:
    """Collects trace data during a pipeline run."""

    def __init__(self, pipeline_id: str, pipeline_name: str, user_id: str):
        self.pipeline_id = pipeline_id
        self.pipeline_name = pipeline_name
        self.user_id = user_id
        self.stages: list[dict[str, Any]] = []

    def record_stage(
        self,
        agent: str,
        latency_ms: int,
        status: str = "completed",
        output_summary: dict | None = None,
        error: str | None = None,
    ) -> None:
        self.stages.append({
            "agent": agent,
            "latency_ms": latency_ms,
            "status": status,
            "output_summary": output_summary or {},
            "error": error,
        })

    def build_record(
        self,
        quality_scores: dict | None = None,
        fact_check_flags: list | None = None,
        iterations_used: int = 0,
        status: str = "completed",
    ) -> dict[str, Any]:
        total_ms = sum(s["latency_ms"] for s in self.stages)
        return {
            "pipeline_id": self.pipeline_id,
            "user_id": self.user_id,
            "pipeline_name": self.pipeline_name,
            "stages": self.stages,
            "total_latency_ms": total_ms,
            "iterations_used": iterations_used,
            "quality_scores": quality_scores or {},
            "fact_check_flags": fact_check_flags or [],
            "status": status,
        }

    def persist(self, db) -> None:
        record = self.build_record()
        try:
            db.table("agent_traces").insert(record).execute()
        except Exception:
            logger.error("Failed to persist agent trace", pipeline_id=self.pipeline_id, exc_info=True)
