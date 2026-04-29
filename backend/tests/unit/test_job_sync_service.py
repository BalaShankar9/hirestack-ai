"""S7-F5: pin app/services/job_sync.py contracts.

Behavioural lock for JobSyncService — alert record shape, score_match
record defaults & 5000-char description truncation, update_match_status
ownership gate, and the get_job_sync_service() singleton identity.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import job_sync as job_sync_module
from app.services.job_sync import JobSyncService, get_job_sync_service


@pytest.fixture
def service():
    db = MagicMock()
    db.create = AsyncMock(return_value="row-1")
    db.get = AsyncMock(return_value={"id": "row-1"})
    db.query = AsyncMock(return_value=[])
    db.update = AsyncMock(return_value=True)
    svc = JobSyncService(db=db)
    svc.ai_client = MagicMock()
    svc.ai_client.complete_json = AsyncMock(
        return_value={
            "match_score": 72,
            "match_reasons": ["Python overlap", "Senior level"],
            "missing_skills": ["Rust"],
            "recommendation": "apply",
        }
    )
    return svc


# ── create_alert ──────────────────────────────────────────────────


class TestCreateAlert:
    @pytest.mark.asyncio
    async def test_record_shape_pinned(self, service):
        await service.create_alert(
            user_id="u1",
            keywords=["python", "ml"],
            location="Remote",
            job_type="full_time",
            salary_min=120000,
            experience_level="senior",
        )
        record = service.db.create.await_args.args[1]
        assert record == {
            "user_id": "u1",
            "keywords": ["python", "ml"],
            "location": "Remote",
            "job_type": "full_time",
            "salary_min": 120000,
            "experience_level": "senior",
            "is_active": True,
        }

    @pytest.mark.asyncio
    async def test_zero_salary_min_becomes_none(self, service):
        # Pinned: salary_min == 0 (default / falsy) is stored as None.
        await service.create_alert(user_id="u", keywords=["x"], salary_min=0)
        record = service.db.create.await_args.args[1]
        assert record["salary_min"] is None

    @pytest.mark.asyncio
    async def test_default_optional_fields_empty_strings(self, service):
        await service.create_alert(user_id="u", keywords=[])
        record = service.db.create.await_args.args[1]
        assert record["location"] == ""
        assert record["job_type"] == ""
        assert record["experience_level"] == ""
        assert record["is_active"] is True


# ── score_match record shape ──────────────────────────────────────


class TestScoreMatchRecord:
    @pytest.mark.asyncio
    async def test_record_uses_ai_result(self, service):
        await service.score_match(
            user_id="u",
            job_title="Engineer",
            company="Acme",
            description="Build stuff",
            location="NYC",
            salary_range="120-150k",
            source_url="https://example.com/job",
            source="linkedin",
            alert_id="alert-1",
        )
        record = service.db.create.await_args.args[1]
        assert record["user_id"] == "u"
        assert record["alert_id"] == "alert-1"
        assert record["title"] == "Engineer"
        assert record["company"] == "Acme"
        assert record["location"] == "NYC"
        assert record["salary_range"] == "120-150k"
        assert record["source_url"] == "https://example.com/job"
        assert record["source"] == "linkedin"
        assert record["match_score"] == 72
        assert record["match_reasons"] == ["Python overlap", "Senior level"]
        # Pinned: status always begins as "new".
        assert record["status"] == "new"

    @pytest.mark.asyncio
    async def test_description_truncated_to_5000(self, service):
        await service.score_match(
            user_id="u",
            job_title="X",
            description="x" * 12_000,
        )
        record = service.db.create.await_args.args[1]
        assert len(record["description"]) == 5000

    @pytest.mark.asyncio
    async def test_missing_ai_keys_use_safe_defaults(self, service):
        # AI returns nothing useful -> match_score=0, reasons=[].
        service.ai_client.complete_json = AsyncMock(return_value={})
        await service.score_match(user_id="u", job_title="X")
        record = service.db.create.await_args.args[1]
        assert record["match_score"] == 0
        assert record["match_reasons"] == []
        assert record["status"] == "new"

    @pytest.mark.asyncio
    async def test_default_source_is_manual(self, service):
        await service.score_match(user_id="u", job_title="X")
        record = service.db.create.await_args.args[1]
        assert record["source"] == "manual"
        # alert_id defaults to None.
        assert record["alert_id"] is None

    @pytest.mark.asyncio
    async def test_ai_prompt_truncates_description_at_2000(self, service):
        await service.score_match(
            user_id="u",
            job_title="X",
            description="y" * 9_000,
        )
        prompt = service.ai_client.complete_json.await_args.kwargs["prompt"]
        # The prompt embeds at most 2000 chars of description.
        # Use a unique-to-description sentinel so we don't collide
        # with "y" characters baked into the prompt template.
        assert "y" * 2000 in prompt
        assert "y" * 2001 not in prompt

    @pytest.mark.asyncio
    async def test_profile_text_built_from_first_primary(self, service):
        service.db.query = AsyncMock(
            return_value=[
                {
                    "title": "Senior Engineer",
                    "skills": [{"name": "python"}, "rust", {"name": "ml"}],
                    "summary": "10y exp",
                }
            ]
        )
        await service.score_match(user_id="u", job_title="X")
        prompt = service.ai_client.complete_json.await_args.kwargs["prompt"]
        assert "Senior Engineer" in prompt
        assert "python" in prompt and "rust" in prompt and "ml" in prompt
        assert "10y exp" in prompt

    @pytest.mark.asyncio
    async def test_no_profile_text_when_no_primary(self, service):
        # query already returns [] in fixture.
        await service.score_match(user_id="u", job_title="X")
        prompt = service.ai_client.complete_json.await_args.kwargs["prompt"]
        assert "No profile available" in prompt

    @pytest.mark.asyncio
    async def test_skills_non_list_yields_empty_skill_section(self, service):
        service.db.query = AsyncMock(
            return_value=[{"title": "T", "skills": "not-a-list", "summary": "s"}]
        )
        await service.score_match(user_id="u", job_title="X")
        prompt = service.ai_client.complete_json.await_args.kwargs["prompt"]
        assert "Skills: \n" in prompt or "Skills: " in prompt


# ── update_match_status ───────────────────────────────────────────


class TestUpdateMatchStatus:
    @pytest.mark.asyncio
    async def test_returns_false_when_match_not_found(self, service):
        service.db.get = AsyncMock(return_value=None)
        out = await service.update_match_status("m1", "u1", "applied")
        assert out is False
        service.db.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_false_when_user_does_not_own_match(self, service):
        service.db.get = AsyncMock(return_value={"id": "m1", "user_id": "OTHER"})
        out = await service.update_match_status("m1", "u1", "applied")
        assert out is False
        service.db.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_updated_for_owner(self, service):
        service.db.get = AsyncMock(return_value={"id": "m1", "user_id": "u1"})
        out = await service.update_match_status("m1", "u1", "saved")
        assert out is True
        update_data = service.db.update.await_args.args[2]
        assert update_data == {"status": "saved"}

    @pytest.mark.asyncio
    async def test_applied_status_adds_iso_timestamp(self, service):
        service.db.get = AsyncMock(return_value={"id": "m1", "user_id": "u1"})
        await service.update_match_status("m1", "u1", "applied")
        update_data = service.db.update.await_args.args[2]
        assert update_data["status"] == "applied"
        assert "applied_at" in update_data
        # ISO 8601 with timezone.
        assert "T" in update_data["applied_at"]
        assert update_data["applied_at"].endswith("+00:00") or "Z" in update_data["applied_at"]

    @pytest.mark.asyncio
    async def test_non_applied_status_omits_applied_at(self, service):
        service.db.get = AsyncMock(return_value={"id": "m1", "user_id": "u1"})
        await service.update_match_status("m1", "u1", "rejected")
        update_data = service.db.update.await_args.args[2]
        assert "applied_at" not in update_data


# ── get_matches filter wiring ─────────────────────────────────────


class TestGetMatches:
    @pytest.mark.asyncio
    async def test_default_only_user_filter(self, service):
        await service.get_matches("u1")
        kwargs = service.db.query.await_args.kwargs
        assert kwargs["filters"] == [("user_id", "==", "u1")]
        # Sorted by match_score DESC.
        assert kwargs["order_by"] == "match_score"
        assert kwargs["order_direction"] == "DESCENDING"
        assert kwargs["limit"] == 50

    @pytest.mark.asyncio
    async def test_status_filter_appended(self, service):
        await service.get_matches("u1", status="applied", limit=10)
        kwargs = service.db.query.await_args.kwargs
        assert ("status", "==", "applied") in kwargs["filters"]
        assert ("user_id", "==", "u1") in kwargs["filters"]
        assert kwargs["limit"] == 10


# ── Singleton ─────────────────────────────────────────────────────


class TestSingleton:
    def setup_method(self):
        # Reset module-level singleton between tests.
        job_sync_module._instance = None

    def teardown_method(self):
        job_sync_module._instance = None

    def test_singleton_identity(self):
        with patch("app.services.job_sync.get_db", return_value=MagicMock()), \
             patch("app.services.job_sync.get_ai_client", return_value=MagicMock()):
            a = get_job_sync_service()
            b = get_job_sync_service()
            assert a is b

    def test_first_call_constructs_instance(self):
        with patch("app.services.job_sync.get_db", return_value=MagicMock()) as gd, \
             patch("app.services.job_sync.get_ai_client", return_value=MagicMock()):
            assert job_sync_module._instance is None
            get_job_sync_service()
            assert job_sync_module._instance is not None
            # Subsequent calls do NOT re-construct (db/ai_client not
            # called again).
            gd.reset_mock()
            get_job_sync_service()
            gd.assert_not_called()
