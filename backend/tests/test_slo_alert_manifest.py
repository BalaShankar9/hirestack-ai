"""S11-F4: SLO alert manifest contract.

Pins that docs/SLO.md contains a machine-readable YAML block with the
required alerts. Future SLO edits must keep this block well-formed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SLO_DOC = REPO_ROOT / "docs" / "SLO.md"

REQUIRED_SLO_NAMES = {
    "pipeline_sync_latency_p95",
    "pipeline_completion_rate",
    "pipeline_error_rate",
    "api_availability",
    "health_p99_ms",
    "model_failovers_burst",
    "error_budget_burn_fast",
}


def _extract_yaml_block() -> str:
    text = SLO_DOC.read_text(encoding="utf-8")
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
    assert m, "docs/SLO.md must contain a ```yaml fenced block (S11-F4)"
    return m.group(1)


def test_slo_doc_exists() -> None:
    assert SLO_DOC.exists(), "docs/SLO.md is the SRE source of truth; do not delete"


def test_slo_doc_has_yaml_alert_manifest() -> None:
    yaml = pytest.importorskip("yaml")
    block = _extract_yaml_block()
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    assert parsed.get("version") == 1
    assert isinstance(parsed.get("slos"), list)
    assert len(parsed["slos"]) >= 7


def test_slo_manifest_required_alerts_present() -> None:
    yaml = pytest.importorskip("yaml")
    parsed = yaml.safe_load(_extract_yaml_block())
    names = {s.get("name") for s in parsed["slos"]}
    missing = REQUIRED_SLO_NAMES - names
    assert not missing, f"SLO manifest missing required alerts: {missing}"


def test_slo_manifest_every_alert_has_severity() -> None:
    yaml = pytest.importorskip("yaml")
    parsed = yaml.safe_load(_extract_yaml_block())
    bad = [s.get("name") for s in parsed["slos"] if s.get("severity") not in ("warn", "page")]
    assert not bad, f"SLOs with missing/invalid severity: {bad}"
