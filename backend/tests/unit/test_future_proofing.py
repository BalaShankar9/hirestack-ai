"""W7 Future-proofing — schema version + feature flags anchor tests."""
from __future__ import annotations

import inspect
import json
import os
from unittest.mock import patch


def test_pipeline_event_schema_version_exported() -> None:
    from app.services.pipeline_runtime import PIPELINE_EVENT_SCHEMA_VERSION
    assert isinstance(PIPELINE_EVENT_SCHEMA_VERSION, str)
    parts = PIPELINE_EVENT_SCHEMA_VERSION.split(".")
    assert len(parts) == 2, f"must be MAJOR.MINOR, got {PIPELINE_EVENT_SCHEMA_VERSION}"
    assert all(p.isdigit() for p in parts)


def test_sse_payload_includes_schema_version() -> None:
    """Every outbound SSE event must carry the schema_version field."""
    from app.services.pipeline_runtime import SSESink, PipelineEvent, PIPELINE_EVENT_SCHEMA_VERSION
    import asyncio

    sink = SSESink()
    ev = PipelineEvent(event_type="progress", phase="atlas", progress=20, message="ok")
    asyncio.run(sink.emit(ev))
    raw = sink.queue.get_nowait()
    # parse 'data: {...}' line
    data_line = [ln for ln in raw.splitlines() if ln.startswith("data: ")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["schema_version"] == PIPELINE_EVENT_SCHEMA_VERSION


def test_sse_agent_status_payload_includes_schema_version() -> None:
    from app.services.pipeline_runtime import SSESink, PipelineEvent, PIPELINE_EVENT_SCHEMA_VERSION
    import asyncio

    sink = SSESink()
    ev = PipelineEvent(
        event_type="agent_status",
        pipeline_name="recon",
        stage="researcher",
        status="running",
    )
    asyncio.run(sink.emit(ev))
    raw = sink.queue.get_nowait()
    data_line = [ln for ln in raw.splitlines() if ln.startswith("data: ")][0]
    payload = json.loads(data_line[len("data: "):])
    assert payload["schema_version"] == PIPELINE_EVENT_SCHEMA_VERSION


def test_feature_flag_truthy_values() -> None:
    from app.core import feature_flags as ff
    ff.reset()
    with patch.dict(os.environ, {"INTEL_PREFETCH_ENABLED": "1"}, clear=False):
        ff.reset()
        assert ff.is_enabled(ff.FLAGS.INTEL_PREFETCH) is True
    for val in ("true", "True", "YES", "on"):
        ff.reset()
        with patch.dict(os.environ, {"INTEL_PREFETCH_ENABLED": val}, clear=False):
            assert ff.is_enabled(ff.FLAGS.INTEL_PREFETCH) is True, val


def test_feature_flag_falsy_and_missing() -> None:
    from app.core import feature_flags as ff
    # explicit false
    for val in ("0", "false", "no", "off", ""):
        ff.reset()
        with patch.dict(os.environ, {"BILLING_ENABLED": val}, clear=False):
            assert ff.is_enabled(ff.FLAGS.BILLING) is False, val
    # unset → default
    ff.reset()
    with patch.dict(os.environ, {}, clear=True):
        # BILLING default is False
        assert ff.is_enabled(ff.FLAGS.BILLING) is False
        # INTEL_PREFETCH default is True
        assert ff.is_enabled(ff.FLAGS.INTEL_PREFETCH) is True


def test_feature_flag_unknown_token_falls_back_to_default() -> None:
    from app.core import feature_flags as ff
    ff.reset()
    with patch.dict(os.environ, {"BILLING_ENABLED": "perhaps"}, clear=False):
        # garbage value → default (False for BILLING)
        assert ff.is_enabled(ff.FLAGS.BILLING) is False
    ff.reset()
    with patch.dict(os.environ, {"INTEL_PREFETCH_ENABLED": "maybe"}, clear=False):
        assert ff.is_enabled(ff.FLAGS.INTEL_PREFETCH) is True


def test_feature_flag_cache_is_populated() -> None:
    from app.core import feature_flags as ff
    ff.reset()
    with patch.dict(os.environ, {"DOC_QUALITY_SCORER_ENABLED": "true"}, clear=False):
        ff.is_enabled(ff.FLAGS.DOC_QUALITY_SCORER)
        # second call should not re-read env even if we change it
        with patch.dict(os.environ, {"DOC_QUALITY_SCORER_ENABLED": "false"}, clear=False):
            assert ff.is_enabled(ff.FLAGS.DOC_QUALITY_SCORER) is True, \
                "cached value must be returned"


def test_feature_flag_snapshot_covers_all_flags() -> None:
    from app.core import feature_flags as ff
    ff.reset()
    snap = ff.snapshot()
    assert "BILLING_ENABLED" in snap
    assert "INTEL_PREFETCH_ENABLED" in snap
    assert "DOC_QUALITY_SCORER_ENABLED" in snap
    assert "WEBHOOK_RETRIES_ENABLED" in snap


def test_feature_flag_module_has_no_side_effects_on_import() -> None:
    """Guard against accidental module-level os.getenv at import time."""
    from app.core import feature_flags as ff
    src = inspect.getsource(ff)
    # Allow module-level imports only; env reads must be inside is_enabled.
    # Coarse check: the only os.getenv call must be inside is_enabled.
    top_level_getenv = [
        line for line in src.splitlines()
        if line.startswith("os.getenv(") or line.startswith("os.environ[")
    ]
    assert not top_level_getenv, "feature_flags must not read env at import time"
