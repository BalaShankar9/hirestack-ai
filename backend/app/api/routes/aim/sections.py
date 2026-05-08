"""AIM \u2014 sections: generate (sync + SSE), fix, output history."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.database import TABLES
from app.services.aim.event_sink import AIMDatabaseSink
from app.services.aim.quota import AIMQuotaService
from app.services.aim.section_service import AIMSectionService
from app.services.pipeline_runtime import (
    PIPELINE_EVENT_SCHEMA_VERSION,
    PipelineEvent,
    SSESink,
)

router = APIRouter()


def _attempt_to_dict(attempt) -> dict[str, Any]:
    return {
        "version": attempt.version,
        "content": attempt.content,
        "blocks": attempt.blocks,
        "word_count": attempt.word_count,
        "weighted_score": attempt.weighted_score,
        "passed_gate": attempt.passed_gate,
        "reviewer": attempt.reviewer,
        "latency_ms": attempt.latency_ms,
    }


@router.post("/sections/{section_id}/generate")
async def generate_section_route(
    section_id: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMSectionService()
    sec = await svc.get_section(current_user["id"], section_id)
    if not sec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="section not found")
    try:
        result = await svc.generate(current_user["id"], section_id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    await AIMQuotaService().record_section_generated(current_user["id"])
    return {
        "section_id": section_id,
        "stop_reason": result.stop_reason,
        "passed_gate": result.final_passed_gate,
        "final": _attempt_to_dict(result.final_attempt),
        "history": [_attempt_to_dict(a) for a in result.history],
    }


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/sections/{section_id}/generate-stream")
async def generate_section_stream(
    section_id: str,
    current_user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """Stream AIM section generation as it happens.

    Wires the AIM orchestrator's per-attempt writer/reviewer events into
    an :class:`SSESink` so the client sees real progress (no end-of-run
    batch dump, no simulated steps). Heartbeats every
    ``HIRESTACK_SSE_HEARTBEAT_SECS`` (default 15s) keep proxies happy.
    """
    svc = AIMSectionService()
    sec = await svc.get_section(current_user["id"], section_id)
    if not sec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="section not found")

    sink = SSESink()
    db_sink = AIMDatabaseSink(section_id=section_id, user_id=current_user["id"])
    user_id = current_user["id"]
    section_title = sec.get("title") or ""
    try:
        from app.core.database import get_db

        db = get_db()
        existing = await db.query(
            TABLES["aim_section_events"],
            filters=[("section_id", "==", section_id), ("user_id", "==", user_id)],
            order_by="sequence",
            order_direction="DESCENDING",
            limit=1,
        )
        next_sequence = int(existing[0]["sequence"]) if existing else 0
    except Exception:  # noqa: BLE001 - stream should still run without history lookup
        next_sequence = 0

    async def adapter(
        event_type: str,
        *,
        agent: str = "",
        status: str = "",
        message: str = "",
        progress: int = 0,
        latency_ms: int = 0,
        data: dict | None = None,
    ) -> None:
        await _emit_both(PipelineEvent(
            event_type=event_type,
            phase=agent,
            stage=agent,
            status=status,
            message=message,
            progress=progress,
            latency_ms=latency_ms,
            pipeline_name="aim",
            data=data or {},
        ))

    async def _emit_both(evt: PipelineEvent) -> None:
        nonlocal next_sequence
        next_sequence += 1
        payload = dict(evt.data or {})
        payload.setdefault("event_id", str(uuid4()))
        payload.setdefault("sequence", next_sequence)
        payload.setdefault("section_id", section_id)
        evt.data = payload
        # SSE first (live UX never blocked by DB latency); persistence is
        # best-effort and never raises into this path.
        await sink.emit(evt)
        try:
            await db_sink.emit(evt)
        except Exception:  # noqa: BLE001
            pass

    async def runner() -> None:
        try:
            result = await svc.generate(user_id, section_id, emit=adapter)
            await _emit_both(PipelineEvent(
                event_type="complete",
                phase="aim",
                stage="aim",
                status="completed",
                progress=100,
                pipeline_name="aim",
                message=("Section ready" if result.final_passed_gate
                         else "Section generated below gate"),
                data={
                    "section_id": section_id,
                    "stop_reason": result.stop_reason,
                    "passed_gate": result.final_passed_gate,
                    "final_version": result.final_attempt.version,
                    "final": _attempt_to_dict(result.final_attempt),
                },
            ))
            try:
                await AIMQuotaService().record_section_generated(user_id)
            except Exception:  # noqa: BLE001 - quota errors must not poison the stream
                pass
        except Exception as e:  # noqa: BLE001 - surfaced via SSE error event
            await _emit_both(PipelineEvent(
                event_type="error",
                phase="aim",
                stage="aim",
                status="failed",
                pipeline_name="aim",
                message=str(e)[:500],
                data={"section_id": section_id},
            ))
        finally:
            await sink.close()

    task = asyncio.create_task(runner())

    async def gen() -> AsyncIterator[str]:
        # Initial envelope so clients can lock onto the section before the
        # first agent event arrives.
        yield _sse("start", {
            "schema_version": PIPELINE_EVENT_SCHEMA_VERSION,
            "section_id": section_id,
            "title": section_title,
            "pipeline_name": "aim",
        })
        heartbeat_interval = float(
            os.environ.get("HIRESTACK_SSE_HEARTBEAT_SECS", "15") or 15
        )
        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        sink.queue.get(), timeout=heartbeat_interval,
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if item is None:
                    break
                yield item
        finally:
            try:
                await task
            except Exception:  # noqa: BLE001 - already surfaced as error event
                pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sections/{section_id}/outputs")
async def list_outputs(
    section_id: str,
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    svc = AIMSectionService()
    if not await svc.get_section(current_user["id"], section_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="section not found")
    return await svc.list_outputs(section_id)


@router.get("/sections/{section_id}/events")
async def list_section_events(
    section_id: str,
    since: int = 0,
    limit: int = 500,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Resume-on-reconnect endpoint.

    Returns persisted ``aim_section_events`` rows with ``sequence > since``,
    ordered ASC by sequence so the client can rehydrate state and then
    re-attach to the live SSE stream without losing or duplicating events.
    """
    svc = AIMSectionService()
    if not await svc.get_section(current_user["id"], section_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="section not found")
    if since < 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            detail="`since` must be >= 0")
    capped_limit = max(1, min(int(limit), 2000))
    from app.core.database import get_db

    db = get_db()
    rows = await db.query(
        TABLES["aim_section_events"],
        filters=[
            ("section_id", "==", section_id),
            ("user_id", "==", current_user["id"]),
            ("sequence", ">", int(since)),
        ],
        order_by="sequence",
        order_direction="ASCENDING",
        limit=capped_limit,
    )
    last_seq = rows[-1]["sequence"] if rows else int(since)
    return {
        "section_id": section_id,
        "since": int(since),
        "count": len(rows),
        "last_sequence": last_seq,
        "events": rows,
    }


class FixRequest(BaseModel):
    draft: str = Field(..., min_length=1, max_length=200_000)


@router.post("/sections/{section_id}/fix")
async def fix_section_route(
    section_id: str,
    payload: FixRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMSectionService()
    if not await svc.get_section(current_user["id"], section_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="section not found")
    return await svc.fix(current_user["id"], section_id, payload.draft)


class ApplyDraftRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=200_000)
    quality_score: float | None = Field(default=None, ge=0, le=100)


@router.post("/sections/{section_id}/outputs/manual", status_code=201)
async def save_manual_output_route(
    section_id: str,
    payload: ApplyDraftRequest,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    svc = AIMSectionService()
    try:
        return await svc.save_manual_output(
            current_user["id"], section_id, payload.content, payload.quality_score
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
