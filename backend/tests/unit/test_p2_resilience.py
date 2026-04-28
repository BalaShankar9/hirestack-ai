"""
Phase 2 Resilience tests — P2-03, P2-06, P2-08, P2-09.

Covers:
  • _is_garbage_input  — garbage detection (P2-09)
  • _truncate_long_jd  — long JD truncation (P2-08)
  • _validate_pipeline_input — min-length, garbage, truncation flags (P2-09/P2-08)
  • empty resume mode  — no_resume_mode flag (P2-06)
  • jobs endpoint usage guard — check_and_reserve called before job creation (P2-03)
"""
import inspect
import pytest


# ═══════════════════════════════════════════════════════════════════════
#  _is_garbage_input
# ═══════════════════════════════════════════════════════════════════════

class TestGarbageInputDetection:
    """Ensure _is_garbage_input catches placeholder/junk text without rejecting real JDs."""

    def _fn(self):
        from app.api.routes.generate import _is_garbage_input
        return _is_garbage_input

    def test_detects_single_char_repeat(self):
        fn = self._fn()
        assert fn("aaaaaaaaaaaaaaaaaaaaaaaaaaaa") is True

    def test_detects_x_repeat(self):
        fn = self._fn()
        assert fn("x" * 100) is True

    def test_detects_digit_repeat(self):
        fn = self._fn()
        assert fn("1" * 50) is True

    def test_accepts_real_jd(self):
        fn = self._fn()
        jd = (
            "We are looking for a Senior Software Engineer with 5+ years of "
            "experience in Python and AWS. You will work on our data platform, "
            "design scalable microservices, and mentor junior engineers. "
            "Requirements: Python, FastAPI, PostgreSQL, Kubernetes. "
            "We offer competitive salary and equity."
        )
        assert fn(jd) is False

    def test_accepts_jd_with_repeated_word(self):
        fn = self._fn()
        # A real JD might say "experience" many times — should not be flagged
        jd = " ".join(["experience"] * 20) + " Python AWS Docker"
        assert fn(jd) is False

    def test_returns_false_for_empty(self):
        fn = self._fn()
        assert fn("") is False
        assert fn("   ") is False

    def test_border_90_percent(self):
        fn = self._fn()
        # At exactly 90%: 90 'a's + 10 other chars → should be flagged (>= 0.9)
        text = "a" * 90 + "bcdefghijk"  # 90 / 100 = 0.9 — flagged
        assert fn(text) is True

        # Just below: 89 'a's + 11 other chars → should NOT be flagged (< 0.9)
        text2 = "a" * 89 + "bcdefghijkl"  # 89 / 100 = 0.89 — not flagged
        assert fn(text2) is False


# ═══════════════════════════════════════════════════════════════════════
#  _truncate_long_jd
# ═══════════════════════════════════════════════════════════════════════

class TestTruncateLongJD:
    """Ensure long JDs are truncated cleanly without cutting mid-word."""

    def _fn(self):
        from app.api.routes.generate import _truncate_long_jd
        return _truncate_long_jd

    def test_short_jd_unchanged(self):
        fn = self._fn()
        text = "Short job description"
        result, truncated = fn(text, max_chars=500)
        assert result == text
        assert truncated is False

    def test_exactly_max_unchanged(self):
        fn = self._fn()
        text = "x" * 500
        result, truncated = fn(text, max_chars=500)
        assert result == text
        assert truncated is False

    def test_long_jd_is_truncated(self):
        fn = self._fn()
        text = "word " * 3000  # ~15 000 chars
        result, truncated = fn(text, max_chars=1000)
        assert truncated is True
        assert len(result) <= 1000

    def test_truncated_result_is_not_empty(self):
        fn = self._fn()
        text = "Some text. " * 2000
        result, truncated = fn(text, max_chars=500)
        assert truncated is True
        assert len(result) > 0

    def test_cuts_at_paragraph_boundary(self):
        """Prefer cutting at a blank-line boundary."""
        fn = self._fn()
        # Build text with a paragraph break near 700 chars in a 1000-char window
        para1 = "A" * 700 + "\n\n"
        para2 = "B" * 400
        text = para1 + para2
        result, truncated = fn(text, max_chars=1000)
        assert truncated is True
        # Should cut at the paragraph break, not mid-text
        assert "B" not in result

    def test_cuts_at_sentence_boundary(self):
        """Fall back to sentence boundary when no paragraph break near cut."""
        fn = self._fn()
        sentence_block = ("The candidate should have strong skills. " * 30)  # ~1 200 chars
        text = sentence_block * 10
        result, truncated = fn(text, max_chars=1000)
        assert truncated is True
        # Should end with ". " or be stripped
        assert result.endswith(".") or result.endswith(".")


# ═══════════════════════════════════════════════════════════════════════
#  _validate_pipeline_input  — new checks
# ═══════════════════════════════════════════════════════════════════════

class TestValidatePipelineInputExtended:
    """Extended _validate_pipeline_input tests for P2-08 / P2-09 features."""

    # Use a realistic JD that passes all validation checks by default
    _VALID_JD = "Looking for a Senior Software Engineer with Python and AWS experience."

    def _req(self, job_title="Engineer", jd_text=None, resume_text=""):
        from app.api.routes.generate import PipelineRequest
        return PipelineRequest(
            job_title=job_title,
            jd_text=jd_text if jd_text is not None else self._VALID_JD,
            resume_text=resume_text,
        )

    def _fn(self):
        from app.api.routes.generate import _validate_pipeline_input
        return _validate_pipeline_input

    # ── Min-length check ──

    def test_rejects_too_short_jd(self):
        from fastapi import HTTPException
        fn = self._fn()
        req = self._req(jd_text="Short job")  # < 20 chars
        with pytest.raises(HTTPException) as exc:
            fn(req)
        assert exc.value.status_code == 400
        assert "too short" in exc.value.detail.lower()

    def test_accepts_jd_at_min_length(self):
        fn = self._fn()
        # A realistic 20-char JD: varied content, not garbage
        req = self._req(jd_text="Engineer Python React")  # exactly 21 chars, all different
        # Should not raise
        fn(req)

    # ── Garbage detection ──

    def test_rejects_garbage_jd(self):
        from fastapi import HTTPException
        fn = self._fn()
        req = self._req(jd_text="x" * 200)
        with pytest.raises(HTTPException) as exc:
            fn(req)
        assert exc.value.status_code == 400
        assert "placeholder" in exc.value.detail.lower() or "test data" in exc.value.detail.lower()

    # ── Truncation ──

    def test_truncates_long_jd_in_place(self):
        from app.api.routes.generate import JD_TRUNCATION_THRESHOLD
        fn = self._fn()
        long_jd = ("We are looking for an experienced engineer. " * 500)  # ~22 000 chars
        assert len(long_jd) > JD_TRUNCATION_THRESHOLD
        req = self._req(jd_text=long_jd)
        flags = fn(req)
        assert flags["jd_truncated"] is True
        assert len(req.jd_text) <= JD_TRUNCATION_THRESHOLD

    def test_no_truncation_for_short_jd(self):
        fn = self._fn()
        req = self._req(jd_text="Looking for a senior engineer with Python and AWS experience.")
        flags = fn(req)
        assert flags["jd_truncated"] is False

    # ── no_resume_mode ──

    def test_no_resume_mode_when_empty_resume(self):
        fn = self._fn()
        req = self._req(resume_text="")
        flags = fn(req)
        assert flags["no_resume_mode"] is True

    def test_no_resume_mode_when_whitespace_resume(self):
        fn = self._fn()
        req = self._req(resume_text="   \n\t  ")
        flags = fn(req)
        assert flags["no_resume_mode"] is True

    def test_resume_mode_when_resume_provided(self):
        fn = self._fn()
        req = self._req(resume_text="I have 5 years of Python experience")
        flags = fn(req)
        assert flags["no_resume_mode"] is False


# ═══════════════════════════════════════════════════════════════════════
#  P2-03: jobs endpoint usage guard
# ═══════════════════════════════════════════════════════════════════════

def test_jobs_route_calls_check_usage_guard():
    """create_generation_job must call check_usage_guard (P2-03 anti-drift)."""
    from app.api.routes.generate import jobs
    src = inspect.getsource(jobs)
    assert "check_usage_guard" in src, (
        "jobs.create_generation_job must call check_usage_guard before creating the job"
    )


def test_jobs_route_calls_record_generation():
    """create_generation_job must call record_generation after job creation (P2-03)."""
    from app.api.routes.generate import jobs
    src = inspect.getsource(jobs)
    assert "record_generation" in src, (
        "jobs.create_generation_job must call record_generation after the job is queued"
    )
