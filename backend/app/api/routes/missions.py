"""M1.api — authenticated CRUD for missions and mission drafts.

Thin route layer over ``public.missions`` and ``public.mission_drafts``:
auth scoping, ownership checks, and fast validation that mirrors the DB
constraints from ``20260509000000_missions_and_drafts.sql``.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.database import TABLES, SupabaseDB, get_db
from app.core.security import limiter
from app.services.mission_control import MissionControlService

logger = logging.getLogger(__name__)
router = APIRouter()

MISSION_STATUSES = {"active", "paused", "archived"}
VOICE_PRESETS = {
    "confident_selective",
    "warm_eager",
    "formal_traditional",
}
DRAFT_STATUSES = {
    "surfaced",
    "prepared",
    "ready_for_user",
    "sent",
    "skipped",
    "expired",
}


class ValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        super().__init__(f"{field}: {reason}")
        self.field = field
        self.reason = reason


def get_db_dep() -> SupabaseDB:
    return get_db()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name}: must be a valid UUID",
        )
    return value


def _map_validation_error(exc: ValidationError) -> HTTPException:
    return HTTPException(status_code=422, detail={"field": exc.field, "reason": exc.reason})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_dt(value: Optional[datetime], field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValidationError(field, "must be a valid datetime")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _normalize_name(value: Optional[str], field: str = "name") -> str:
    if value is None:
        raise ValidationError(field, "is required")
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValidationError(field, "must not be empty")
    if len(cleaned) > 200:
        raise ValidationError(field, "must be ≤ 200 chars")
    return cleaned


def _normalize_choice(value: Optional[str], *, field: str, allowed: Sequence[str]) -> str:
    if value is None:
        raise ValidationError(field, "is required")
    cleaned = value.strip().lower()
    if cleaned not in allowed:
        raise ValidationError(field, f"must be one of: {', '.join(sorted(allowed))}")
    return cleaned


def _normalize_text_list(values: Optional[List[str]], field: str) -> List[str]:
    if values is None:
        return []
    cleaned: List[str] = []
    seen: set[str] = set()
    for item in values:
        text = " ".join(str(item or "").split())
        if not text:
            continue
        if len(text) > 200:
            raise ValidationError(field, "items must be ≤ 200 chars")
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
    return cleaned


def _normalize_optional_int(
    value: Optional[int],
    *,
    field: str,
    minimum: int = 0,
    maximum: Optional[int] = None,
) -> Optional[int]:
    if value is None:
        return None
    number = int(value)
    if number < minimum:
        raise ValidationError(field, f"must be ≥ {minimum}")
    if maximum is not None and number > maximum:
        raise ValidationError(field, f"must be ≤ {maximum}")
    return number


def _normalize_score(value: Optional[float], *, field: str) -> Optional[float]:
    if value is None:
        return None
    score = round(float(value), 1)
    if score < 0 or score > 5:
        raise ValidationError(field, "must be between 0 and 5")
    return score


def _validate_comp_band(min_value: Optional[int], max_value: Optional[int]) -> None:
    if min_value is not None and max_value is not None and max_value < min_value:
        raise ValidationError("comp_band_max", "must be ≥ comp_band_min")


def _apply_draft_status_defaults(
    *,
    status: Optional[str],
    surfaced_at: Optional[str],
    prepared_at: Optional[str],
    sent_at: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    surfaced = surfaced_at or _now_iso()
    prepared = prepared_at
    sent = sent_at
    if status in {"prepared", "ready_for_user", "sent"} and prepared is None:
        prepared = _now_iso()
    if status == "sent" and sent is None:
        sent = _now_iso()
    return surfaced, prepared, sent


class CreateMissionRequest(BaseModel):
    name: str
    status: str = "active"
    role_titles: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    comp_band_min: Optional[int] = None
    comp_band_max: Optional[int] = None
    must_haves: List[str] = Field(default_factory=list)
    deal_breakers: List[str] = Field(default_factory=list)
    min_fit_score: float = 4.0
    target_volume_per_week: int = 5
    voice_preset: str = "confident_selective"


class PatchMissionRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    role_titles: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    comp_band_min: Optional[int] = None
    comp_band_max: Optional[int] = None
    must_haves: Optional[List[str]] = None
    deal_breakers: Optional[List[str]] = None
    min_fit_score: Optional[float] = None
    target_volume_per_week: Optional[int] = None
    voice_preset: Optional[str] = None


class CreateMissionDraftRequest(BaseModel):
    application_id: Optional[str] = None
    surfaced_at: Optional[datetime] = None
    prepared_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    status: str = "surfaced"
    fit_score: Optional[float] = None


class PatchMissionDraftRequest(BaseModel):
    application_id: Optional[str] = None
    surfaced_at: Optional[datetime] = None
    prepared_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    status: Optional[str] = None
    fit_score: Optional[float] = None


def _build_mission_row(body: CreateMissionRequest) -> Dict[str, Any]:
    status = _normalize_choice(body.status, field="status", allowed=MISSION_STATUSES)
    comp_band_min = _normalize_optional_int(body.comp_band_min, field="comp_band_min")
    comp_band_max = _normalize_optional_int(body.comp_band_max, field="comp_band_max")
    _validate_comp_band(comp_band_min, comp_band_max)
    return {
        "name": _normalize_name(body.name),
        "status": status,
        "role_titles": _normalize_text_list(body.role_titles, "role_titles"),
        "locations": _normalize_text_list(body.locations, "locations"),
        "comp_band_min": comp_band_min,
        "comp_band_max": comp_band_max,
        "must_haves": _normalize_text_list(body.must_haves, "must_haves"),
        "deal_breakers": _normalize_text_list(body.deal_breakers, "deal_breakers"),
        "min_fit_score": _normalize_score(body.min_fit_score, field="min_fit_score"),
        "target_volume_per_week": _normalize_optional_int(
            body.target_volume_per_week,
            field="target_volume_per_week",
            minimum=1,
            maximum=100,
        ),
        "voice_preset": _normalize_choice(
            body.voice_preset,
            field="voice_preset",
            allowed=VOICE_PRESETS,
        ),
        "paused_at": _now_iso() if status == "paused" else None,
    }


def _build_mission_update(body: PatchMissionRequest, existing: Dict[str, Any]) -> Dict[str, Any]:
    provided = body.model_fields_set
    update: Dict[str, Any] = {}

    try:
        if "name" in provided:
            update["name"] = _normalize_name(body.name)
        if "status" in provided:
            update["status"] = _normalize_choice(body.status, field="status", allowed=MISSION_STATUSES)
        if "role_titles" in provided:
            update["role_titles"] = _normalize_text_list(body.role_titles, "role_titles")
        if "locations" in provided:
            update["locations"] = _normalize_text_list(body.locations, "locations")
        if "must_haves" in provided:
            update["must_haves"] = _normalize_text_list(body.must_haves, "must_haves")
        if "deal_breakers" in provided:
            update["deal_breakers"] = _normalize_text_list(body.deal_breakers, "deal_breakers")
        if "comp_band_min" in provided:
            update["comp_band_min"] = _normalize_optional_int(body.comp_band_min, field="comp_band_min")
        if "comp_band_max" in provided:
            update["comp_band_max"] = _normalize_optional_int(body.comp_band_max, field="comp_band_max")
        if "min_fit_score" in provided:
            update["min_fit_score"] = _normalize_score(body.min_fit_score, field="min_fit_score")
        if "target_volume_per_week" in provided:
            update["target_volume_per_week"] = _normalize_optional_int(
                body.target_volume_per_week,
                field="target_volume_per_week",
                minimum=1,
                maximum=100,
            )
        if "voice_preset" in provided:
            update["voice_preset"] = _normalize_choice(
                body.voice_preset,
                field="voice_preset",
                allowed=VOICE_PRESETS,
            )
    except ValidationError:
        raise

    min_value = update.get("comp_band_min", existing.get("comp_band_min"))
    max_value = update.get("comp_band_max", existing.get("comp_band_max"))
    _validate_comp_band(min_value, max_value)

    next_status = update.get("status")
    if next_status == "paused":
        update["paused_at"] = existing.get("paused_at") or _now_iso()
    elif next_status in {"active", "archived"} and existing.get("status") == "paused":
        update["paused_at"] = None

    return update


def _build_draft_row(body: CreateMissionDraftRequest) -> Dict[str, Any]:
    application_id = body.application_id
    if application_id is not None:
        application_id = _validate_uuid(application_id, "application_id")
    status = _normalize_choice(body.status, field="status", allowed=DRAFT_STATUSES)
    surfaced_at, prepared_at, sent_at = _apply_draft_status_defaults(
        status=status,
        surfaced_at=_serialize_dt(body.surfaced_at, "surfaced_at"),
        prepared_at=_serialize_dt(body.prepared_at, "prepared_at"),
        sent_at=_serialize_dt(body.sent_at, "sent_at"),
    )
    return {
        "application_id": application_id,
        "surfaced_at": surfaced_at,
        "prepared_at": prepared_at,
        "sent_at": sent_at,
        "status": status,
        "fit_score": _normalize_score(body.fit_score, field="fit_score"),
    }


def _build_draft_update(body: PatchMissionDraftRequest, existing: Dict[str, Any]) -> Dict[str, Any]:
    provided = body.model_fields_set
    update: Dict[str, Any] = {}

    if "application_id" in provided:
        if body.application_id is None:
            update["application_id"] = None
        else:
            update["application_id"] = _validate_uuid(body.application_id, "application_id")
    if "status" in provided:
        update["status"] = _normalize_choice(body.status, field="status", allowed=DRAFT_STATUSES)
    if "fit_score" in provided:
        update["fit_score"] = _normalize_score(body.fit_score, field="fit_score")
    if "surfaced_at" in provided:
        update["surfaced_at"] = _serialize_dt(body.surfaced_at, "surfaced_at")
    if "prepared_at" in provided:
        update["prepared_at"] = _serialize_dt(body.prepared_at, "prepared_at")
    if "sent_at" in provided:
        update["sent_at"] = _serialize_dt(body.sent_at, "sent_at")

    status = update.get("status", existing.get("status"))
    surfaced_at = update.get("surfaced_at", existing.get("surfaced_at"))
    prepared_at = update.get("prepared_at", existing.get("prepared_at"))
    sent_at = update.get("sent_at", existing.get("sent_at"))
    surfaced_at, prepared_at, sent_at = _apply_draft_status_defaults(
        status=status,
        surfaced_at=surfaced_at,
        prepared_at=prepared_at,
        sent_at=sent_at,
    )
    update.setdefault("surfaced_at", surfaced_at)
    update.setdefault("prepared_at", prepared_at)
    update.setdefault("sent_at", sent_at)
    return update


async def _get_owned_mission_or_404(db: SupabaseDB, mission_id: str, user_id: str) -> Dict[str, Any]:
    mission_id = _validate_uuid(mission_id, "mission_id")
    row = await db.get(TABLES["missions"], mission_id)
    if not row or row.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Mission not found")
    return row


async def _get_owned_draft_or_404(
    db: SupabaseDB,
    draft_id: str,
    mission_id: str,
    user_id: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    draft_id = _validate_uuid(draft_id, "draft_id")
    mission = await _get_owned_mission_or_404(db, mission_id, user_id)
    row = await db.get(TABLES["mission_drafts"], draft_id)
    if not row or row.get("mission_id") != mission["id"]:
        raise HTTPException(status_code=404, detail="Mission draft not found")
    return row, mission


@router.get("/missions")
@limiter.limit("30/minute")
async def list_missions(
    request: Request,
    status: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    filters = [("user_id", "==", current_user["id"])]
    if status is not None:
        filters.append(("status", "==", _normalize_choice(status, field="status", allowed=MISSION_STATUSES)))
    rows = await db.query(
        TABLES["missions"],
        filters=filters,
        order_by="created_at",
        order_direction="DESCENDING",
    )
    return {"items": rows, "count": len(rows)}


@router.post("/missions", status_code=201)
@limiter.limit("10/minute")
async def create_mission(
    request: Request,
    body: CreateMissionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    try:
        row = _build_mission_row(body)
    except ValidationError as exc:
        raise _map_validation_error(exc)
    row["user_id"] = current_user["id"]
    new_id = await db.create(TABLES["missions"], row)
    created = await db.get(TABLES["missions"], new_id)
    return created or {"id": new_id, **row}


@router.get("/missions/{mission_id}")
@limiter.limit("30/minute")
async def get_mission(
    request: Request,
    mission_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    return await _get_owned_mission_or_404(db, mission_id, current_user["id"])


@router.patch("/missions/{mission_id}")
@limiter.limit("10/minute")
async def patch_mission(
    request: Request,
    mission_id: str,
    body: PatchMissionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    existing = await _get_owned_mission_or_404(db, mission_id, current_user["id"])
    try:
        update = _build_mission_update(body, existing)
    except ValidationError as exc:
        raise _map_validation_error(exc)
    if not update:
        return existing
    ok = await db.update(TABLES["missions"], mission_id, update)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update mission")
    refreshed = await db.get(TABLES["missions"], mission_id)
    return refreshed or {**existing, **update}


@router.delete("/missions/{mission_id}")
@limiter.limit("10/minute")
async def delete_mission(
    request: Request,
    mission_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, str]:
    mission = await _get_owned_mission_or_404(db, mission_id, current_user["id"])
    ok = await db.delete(TABLES["missions"], mission["id"])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to delete mission")
    return {"status": "deleted", "id": mission["id"]}


@router.get("/missions/{mission_id}/drafts")
@limiter.limit("30/minute")
async def list_mission_drafts(
    request: Request,
    mission_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    mission = await _get_owned_mission_or_404(db, mission_id, current_user["id"])
    normalized_status: Optional[str] = None
    if status is not None:
        normalized_status = _normalize_choice(status, field="status", allowed=DRAFT_STATUSES)
    rows = await MissionControlService(db=db).list_enriched_drafts(
        mission,
        user_id=current_user["id"],
        status=normalized_status,
        limit=limit,
    )
    return {"items": rows, "count": len(rows), "mission_id": mission["id"]}


@router.post("/missions/{mission_id}/sync")
@limiter.limit("10/minute")
async def sync_mission_drafts(
    request: Request,
    mission_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    mission = await _get_owned_mission_or_404(db, mission_id, current_user["id"])
    return await MissionControlService(db=db).sync_mission(
        mission,
        user_id=current_user["id"],
    )


@router.post("/missions/{mission_id}/drafts", status_code=201)
@limiter.limit("10/minute")
async def create_mission_draft(
    request: Request,
    mission_id: str,
    body: CreateMissionDraftRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    mission = await _get_owned_mission_or_404(db, mission_id, current_user["id"])
    control = MissionControlService(db=db)
    try:
        row = _build_draft_row(body)
    except ValidationError as exc:
        raise _map_validation_error(exc)
    row["mission_id"] = mission["id"]
    try:
        new_id = await db.create(TABLES["mission_drafts"], row)
    except Exception as exc:
        msg = str(exc).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            raise HTTPException(
                status_code=409,
                detail={
                    "field": "application_id",
                    "reason": "this application is already attached to the mission",
                },
            )
        logger.exception("missions.create_draft failed")
        raise
    created = await db.get(TABLES["mission_drafts"], new_id)
    draft = created or {"id": new_id, **row}
    return await control.enrich_draft(draft, user_id=current_user["id"])


@router.get("/missions/{mission_id}/drafts/{draft_id}")
@limiter.limit("30/minute")
async def get_mission_draft(
    request: Request,
    mission_id: str,
    draft_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    draft, _mission = await _get_owned_draft_or_404(db, draft_id, mission_id, current_user["id"])
    return await MissionControlService(db=db).enrich_draft(draft, user_id=current_user["id"])


@router.patch("/missions/{mission_id}/drafts/{draft_id}")
@limiter.limit("10/minute")
async def patch_mission_draft(
    request: Request,
    mission_id: str,
    draft_id: str,
    body: PatchMissionDraftRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    existing, mission = await _get_owned_draft_or_404(db, draft_id, mission_id, current_user["id"])
    control = MissionControlService(db=db)
    try:
        update = _build_draft_update(body, existing)
    except ValidationError as exc:
        raise _map_validation_error(exc)
    if not update:
        return existing
    if update.get("application_id") and update["application_id"] != existing.get("application_id"):
        siblings = await db.query(
            TABLES["mission_drafts"],
            filters=[("mission_id", "==", mission["id"]), ("application_id", "==", update["application_id"])],
            limit=1,
        )
        if siblings and siblings[0].get("id") != existing.get("id"):
            raise HTTPException(
                status_code=409,
                detail={
                    "field": "application_id",
                    "reason": "this application is already attached to the mission",
                },
            )
    ok = await db.update(TABLES["mission_drafts"], draft_id, update)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update mission draft")
    refreshed = await db.get(TABLES["mission_drafts"], draft_id)
    draft = refreshed or {**existing, **update}
    return await control.enrich_draft(draft, user_id=current_user["id"])


@router.delete("/missions/{mission_id}/drafts/{draft_id}")
@limiter.limit("10/minute")
async def delete_mission_draft(
    request: Request,
    mission_id: str,
    draft_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, str]:
    draft, _mission = await _get_owned_draft_or_404(db, draft_id, mission_id, current_user["id"])
    ok = await db.delete(TABLES["mission_drafts"], draft["id"])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to delete mission draft")
    return {"status": "deleted", "id": draft["id"]}