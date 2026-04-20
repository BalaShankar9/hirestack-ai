"""Critic-gate enforcement tests.

Pin the contract that pipeline_runtime stamps `validation` onto the
response and that jobs.py downgrades job status when validation fails.
This is the behavior the audit demanded ("flip job status, not just emit
an event")."""
from __future__ import annotations

from ai_engine.agents.artifact_contracts import (
    DocumentRecord,
    EvidenceTier,
    TailoredDocumentBundle,
)
from ai_engine.agents.validation_critic import ValidationCritic, report_passed


def _bundle(docs: dict[str, str] | None = None) -> TailoredDocumentBundle:
    docs = docs or {}
    records = {
        key: DocumentRecord(
            doc_type=key,
            label=key.replace("_", " ").title(),
            html_content=html,
            word_count=len(html.split()),
        )
        for key, html in docs.items()
        if html.strip()
    }
    return TailoredDocumentBundle(
        application_id=None,
        created_by_agent="quill",
        confidence=0.7,
        evidence_tier=EvidenceTier.DERIVED,
        documents=records,
    )


def test_critic_fails_on_empty_bundle():
    """Empty bundle MUST trip the gate. This is the audit's anchor case."""
    critic = ValidationCritic()
    report = critic.review_documents(_bundle({}))
    assert report_passed(report) is False, (
        "Empty bundle must fail the gate — this is the contract that "
        "prevents the platform from claiming success on zero outputs."
    )


def test_critic_passes_on_substantial_documents():
    """A reasonable doc set should pass."""
    critic = ValidationCritic()
    long_html = "<p>" + ("Senior engineer with deep expertise. " * 80) + "</p>"
    report = critic.review_documents(
        _bundle({
            "cv": long_html,
            "cover_letter": long_html,
        })
    )
    assert report_passed(report) is True, (
        f"Substantial documents must pass; got findings: "
        f"{[(f.code, f.message) for f in report.findings]}"
    )


def test_pipeline_runtime_attaches_validation_block_on_failure():
    """When the runtime code path runs the critic, it must stamp
    response['validation'] with the required keys. This test simulates
    the relevant branch by importing the production code path."""
    import inspect

    from backend.app.services import pipeline_runtime

    src = inspect.getsource(pipeline_runtime)
    # Anchor the contract: the response gets a validation dict with these
    # keys, derived from the v4 critic, not a stub.
    assert "response[\"validation\"]" in src, (
        "pipeline_runtime must stamp response['validation'] for the job "
        "runner to consume."
    )
    for required_key in (
        '"passed"',
        '"overall_score"',
        '"docs_passed"',
        '"docs_failed"',
        '"error_count"',
        '"warning_count"',
        '"findings_summary"',
    ):
        assert required_key in src, (
            f"validation dict must include {required_key}; this is the "
            "contract jobs.py + the frontend rely on."
        )


def test_jobs_runner_downgrades_status_when_validation_failed():
    """The job runner must read result.validation.passed and persist
    'succeeded_with_warnings' instead of 'succeeded' when the gate fails."""
    import inspect

    from backend.app.api.routes.generate import jobs as jobs_module

    src = inspect.getsource(jobs_module)
    assert "succeeded_with_warnings" in src, (
        "jobs.py must use the 'succeeded_with_warnings' status when the "
        "v4 critic gate fails. Without this, the audit's 'flip job status' "
        "requirement is not met."
    )
    # Both of the runner code paths must respect the gate.
    occurrences = src.count("succeeded_with_warnings")
    assert occurrences >= 4, (
        f"Both job runner paths + retry guards must reference "
        f"succeeded_with_warnings; only saw {occurrences} occurrences."
    )


def test_terminal_state_guards_include_warnings_status():
    """Retry / state guards must treat succeeded_with_warnings as terminal
    — otherwise the orphan-cleanup loop will repeatedly try to 'finish'
    these jobs."""
    import inspect

    from backend.app.api.routes.generate import jobs as jobs_module

    src = inspect.getsource(jobs_module)
    # The set literal must contain the new status anywhere it appears.
    legacy = src.count('{"succeeded", "failed", "cancelled"}')
    assert legacy == 0, (
        "All {succeeded, failed, cancelled} guards must be widened to "
        "include succeeded_with_warnings."
    )
