"""
Stage contracts — typed schemas for every agent pipeline stage.

These contracts define the canonical shapes that stage outputs must conform to.
They are NOT Pydantic models (no runtime overhead); they are TypedDict + validation
helpers used at stage boundaries to catch contract drift early.
"""
from __future__ import annotations

from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
#  Contract validation helpers
# ═══════════════════════════════════════════════════════════════════════

class ContractViolation(Exception):
    """Raised when a stage output does not match its contract."""
    def __init__(self, stage: str, field: str, message: str):
        self.stage = stage
        self.field = field
        super().__init__(f"[{stage}] {field}: {message}")


def _check_required(data: dict, stage: str, required_keys: list[str]) -> list[str]:
    """Return list of missing required keys."""
    return [k for k in required_keys if k not in data]


def _check_type(data: dict, stage: str, key: str, expected_type: type) -> Optional[str]:
    """Return error message if key exists but has wrong type."""
    val = data.get(key)
    if val is not None and not isinstance(val, expected_type):
        return f"Expected {expected_type.__name__}, got {type(val).__name__}"
    return None


# ═══════════════════════════════════════════════════════════════════════
#  Researcher contract
# ═══════════════════════════════════════════════════════════════════════

RESEARCHER_REQUIRED_KEYS = [
    "industry",
    "keyword_priority",
    "key_signals",
    "coverage_score",
    "tool_results",
]

def validate_researcher_output(content: dict) -> list[str]:
    """Validate researcher output matches expected contract.

    Returns list of issues (empty = valid).
    """
    issues: list[str] = []
    missing = _check_required(content, "researcher", RESEARCHER_REQUIRED_KEYS)
    if missing:
        issues.append(f"Missing required keys: {missing}")

    if "tool_results" in content and not isinstance(content["tool_results"], dict):
        issues.append("tool_results must be a dict")

    score = content.get("coverage_score")
    if score is not None and not isinstance(score, (int, float)):
        issues.append(f"coverage_score must be numeric, got {type(score).__name__}")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  Drafter contract
# ═══════════════════════════════════════════════════════════════════════

DRAFTER_REQUIRED_KEYS = ["html"]

def validate_drafter_output(content: dict) -> list[str]:
    """Validate drafter output matches expected contract."""
    issues: list[str] = []
    missing = _check_required(content, "drafter", DRAFTER_REQUIRED_KEYS)
    if missing:
        issues.append(f"Missing required keys: {missing}")

    html = content.get("html")
    if html is not None and not isinstance(html, str):
        issues.append(f"html must be a string, got {type(html).__name__}")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  Critic contract
# ═══════════════════════════════════════════════════════════════════════

CRITIC_REQUIRED_KEYS = [
    "quality_scores",
    "needs_revision",
    "feedback",
    "confidence",
]

QUALITY_SCORE_DIMENSIONS = ["impact", "clarity", "tone_match", "completeness"]

def validate_critic_output(content: dict) -> list[str]:
    """Validate critic output matches expected contract."""
    issues: list[str] = []
    missing = _check_required(content, "critic", CRITIC_REQUIRED_KEYS)
    if missing:
        issues.append(f"Missing required keys: {missing}")

    scores = content.get("quality_scores", {})
    if isinstance(scores, dict):
        for dim in QUALITY_SCORE_DIMENSIONS:
            if dim not in scores:
                issues.append(f"quality_scores missing dimension: {dim}")

    feedback = content.get("feedback", {})
    if isinstance(feedback, dict):
        if "critical_issues" not in feedback:
            issues.append("feedback missing critical_issues list")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  Optimizer contract
# ═══════════════════════════════════════════════════════════════════════

OPTIMIZER_REQUIRED_KEYS = [
    "keyword_analysis",
    "readability_score",
    "suggestions",
    "confidence",
]

def validate_optimizer_output(content: dict) -> list[str]:
    """Validate optimizer output matches expected contract."""
    issues: list[str] = []
    missing = _check_required(content, "optimizer", OPTIMIZER_REQUIRED_KEYS)
    if missing:
        issues.append(f"Missing required keys: {missing}")

    kw = content.get("keyword_analysis", {})
    if isinstance(kw, dict):
        for subkey in ["present", "missing"]:
            if subkey not in kw:
                issues.append(f"keyword_analysis missing '{subkey}' list")

    suggestions = content.get("suggestions")
    if suggestions is not None and not isinstance(suggestions, list):
        issues.append(f"suggestions must be a list, got {type(suggestions).__name__}")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  FactChecker contract
# ═══════════════════════════════════════════════════════════════════════

FACT_CHECKER_REQUIRED_KEYS = [
    "claims",
    "summary",
    "overall_accuracy",
    "confidence",
]

VALID_CLAIM_CLASSIFICATIONS = {
    "verified", "inferred", "embellished", "fabricated",
    "supported", "unsupported", "enhanced",
}

def validate_fact_checker_output(content: dict) -> list[str]:
    """Validate fact-checker output matches expected contract."""
    issues: list[str] = []
    missing = _check_required(content, "fact_checker", FACT_CHECKER_REQUIRED_KEYS)
    if missing:
        issues.append(f"Missing required keys: {missing}")

    claims = content.get("claims", [])
    if isinstance(claims, list):
        for i, claim in enumerate(claims):
            if not isinstance(claim, dict):
                issues.append(f"claims[{i}] must be a dict")
                continue
            if "text" not in claim:
                issues.append(f"claims[{i}] missing 'text'")
            cls = claim.get("classification", "")
            if cls and cls not in VALID_CLAIM_CLASSIFICATIONS:
                issues.append(f"claims[{i}] unknown classification: {cls}")

    summary = content.get("summary", {})
    if isinstance(summary, dict):
        for key in ["verified", "fabricated"]:
            if key not in summary:
                issues.append(f"summary missing '{key}' count")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  Validator contract
# ═══════════════════════════════════════════════════════════════════════

VALIDATOR_REQUIRED_KEYS = [
    "valid",
    "checks",
    "issues",
]

def validate_validator_output(content: dict) -> list[str]:
    """Validate validator output matches expected contract."""
    issues_list: list[str] = []
    missing = _check_required(content, "validator", VALIDATOR_REQUIRED_KEYS)
    if missing:
        issues_list.append(f"Missing required keys: {missing}")

    checks = content.get("checks", {})
    if isinstance(checks, dict):
        for key in ["schema_compliant", "format_valid"]:
            if key not in checks:
                issues_list.append(f"checks missing '{key}'")

    doc_issues = content.get("issues", [])
    if isinstance(doc_issues, list):
        for i, issue in enumerate(doc_issues):
            if isinstance(issue, dict) and "severity" not in issue:
                issues_list.append(f"issues[{i}] missing 'severity'")

    return issues_list


# ═══════════════════════════════════════════════════════════════════════
#  Optimizer Final Analysis contract
# ═══════════════════════════════════════════════════════════════════════

OPTIMIZER_FINAL_ANALYSIS_REQUIRED_KEYS = [
    "initial_ats_score",
    "final_ats_score",
    "keyword_gap_delta",
    "final_readability",
    "readability_delta",
    "remaining_missing_keywords",
    "residual_recommendations",
    "residual_issue_count",
]

def validate_optimizer_final_analysis_output(content: dict) -> list[str]:
    """Validate optimizer final analysis output matches expected contract."""
    issues: list[str] = []
    missing = _check_required(content, "optimizer_final_analysis", OPTIMIZER_FINAL_ANALYSIS_REQUIRED_KEYS)
    if missing:
        issues.append(f"Missing required keys: {missing}")

    for score_key in ["initial_ats_score", "final_ats_score", "final_readability"]:
        val = content.get(score_key)
        if val is not None and not isinstance(val, (int, float)):
            issues.append(f"{score_key} must be numeric, got {type(val).__name__}")

    recs = content.get("residual_recommendations")
    if recs is not None and not isinstance(recs, list):
        issues.append(f"residual_recommendations must be a list, got {type(recs).__name__}")

    missing_kws = content.get("remaining_missing_keywords")
    if missing_kws is not None and not isinstance(missing_kws, list):
        issues.append(f"remaining_missing_keywords must be a list, got {type(missing_kws).__name__}")

    return issues


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline result contract
# ═══════════════════════════════════════════════════════════════════════

PIPELINE_RESULT_REQUIRED_KEYS = ["html"]

def validate_pipeline_result(content: dict) -> list[str]:
    """Validate final pipeline result content matches expected contract."""
    issues: list[str] = []
    missing = _check_required(content, "pipeline_result", PIPELINE_RESULT_REQUIRED_KEYS)
    if missing:
        issues.append(f"Missing required keys: {missing}")
    return issues


# ═══════════════════════════════════════════════════════════════════════
#  Stage boundary validator (for use in orchestrator)
# ═══════════════════════════════════════════════════════════════════════

_STAGE_VALIDATORS = {
    "researcher": validate_researcher_output,
    "drafter": validate_drafter_output,
    "critic": validate_critic_output,
    "optimizer": validate_optimizer_output,
    "optimizer_final_analysis": validate_optimizer_final_analysis_output,
    "fact_checker": validate_fact_checker_output,
    "validator": validate_validator_output,
}


def validate_stage_output(stage_name: str, content: dict, *, strict: bool = False) -> list[str]:
    """Validate a stage's output content against its contract.

    Args:
        stage_name: Name of the pipeline stage.
        content: The AgentResult.content dict.
        strict: If True, raises ContractViolation on first issue.

    Returns:
        List of contract issues (empty = valid).
    """
    # Normalize stage name (e.g. "drafter_revision_1" → "drafter")
    normalized = stage_name.lower()

    # Check for exact match first (e.g. "optimizer_final_analysis")
    if normalized in _STAGE_VALIDATORS:
        base_name = normalized
    elif normalized.startswith("fact_checker"):
        base_name = "fact_checker"
    elif normalized.startswith("drafter"):
        base_name = "drafter"
    elif normalized.startswith("critic"):
        base_name = "critic"
    elif normalized.startswith("optimizer"):
        base_name = "optimizer"
    elif normalized.startswith("researcher"):
        base_name = "researcher"
    elif normalized.startswith("validator"):
        base_name = "validator"
    else:
        base_name = stage_name.split("_")[0]

    validator_fn = _STAGE_VALIDATORS.get(base_name)
    if not validator_fn:
        return []

    issues = validator_fn(content)
    if strict and issues:
        raise ContractViolation(stage_name, "output", "; ".join(issues))
    return issues
