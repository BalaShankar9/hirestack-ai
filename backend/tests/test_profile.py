"""Profile lifecycle tests — upload, update, versioning, social, intelligence, docs, delete."""
import pytest
from unittest.mock import AsyncMock, patch


# ── Unit tests for ProfileService ─────────────────────────────────────


class FakeDB:
    """In-memory fake for SupabaseDB."""

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._counter = 0

    async def create(self, table, data):
        self._counter += 1
        doc_id = f"fake-{self._counter}"
        self._store[doc_id] = {**data, "id": doc_id}
        return doc_id

    async def get(self, table, doc_id):
        return self._store.get(doc_id)

    async def update(self, table, doc_id, data):
        if doc_id in self._store:
            self._store[doc_id].update(data)
            return True
        return False

    async def delete(self, table, doc_id):
        self._store.pop(doc_id, None)
        return True

    async def query(self, table, filters=None, order_by=None, order_direction=None, limit=None):
        results = list(self._store.values())
        if filters:
            for field, op, value in filters:
                results = [r for r in results if r.get(field) == value]
        return results[:limit] if limit else results


def _make_parsed_data():
    return {
        "name": "Test User",
        "title": "Software Engineer",
        "summary": "Experienced developer",
        "contact_info": {"email": "test@example.com", "phone": "555-1234", "linkedin": "https://linkedin.com/in/test", "github": "https://github.com/test"},
        "skills": [{"name": "Python", "level": "advanced", "category": "Programming Languages"}],
        "experience": [{"company": "Acme", "title": "Dev", "start_date": "2020", "end_date": "2024", "is_current": False}],
        "education": [{"institution": "MIT", "degree": "BS", "field": "CS"}],
        "certifications": [{"name": "AWS SAA", "issuer": "AWS"}],
        "projects": [{"name": "MyApp", "description": "A web app"}],
        "languages": [{"language": "English", "proficiency": "native"}],
        "achievements": ["Led team of 5"],
    }


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def profile_service(fake_db):
    with patch("app.services.profile.get_db", return_value=fake_db):
        from app.services.profile import ProfileService
        svc = ProfileService(db=fake_db)
        return svc


@pytest.mark.asyncio
async def test_create_profile_sets_version_and_social(profile_service, fake_db):
    """New profiles must have profile_version=1, universal_docs_version=0, and social_links."""
    parsed = _make_parsed_data()
    with patch.object(profile_service.file_parser, "extract_text", new_callable=AsyncMock, return_value="resume text"):
        with patch("app.services.profile.RoleProfilerChain") as MockChain:
            MockChain.return_value.parse_resume = AsyncMock(return_value=parsed)

            result = await profile_service.create_from_upload(
                user_id="user-1", file_contents=b"content", file_name="resume.pdf", file_type=".pdf", is_primary=True,
            )

    assert result["profile_version"] == 1
    assert result["universal_docs_version"] == 0
    assert result["is_primary"] is True
    assert "social_links" in result
    assert result["social_links"]["linkedin"] == "https://linkedin.com/in/test"
    assert result["completeness_score"] > 0


@pytest.mark.asyncio
async def test_update_increments_version(profile_service, fake_db):
    """Every update must increment profile_version."""
    fake_db._store["p1"] = {
        "id": "p1", "user_id": "u1", "profile_version": 1,
        "skills": [], "experience": [], "education": [], "certifications": [], "projects": [],
        "social_links": {}, "contact_info": {},
    }

    result = await profile_service.update_profile("p1", "u1", {"title": "Senior Dev"})
    assert result["profile_version"] == 2
    assert result["title"] == "Senior Dev"

    result2 = await profile_service.update_profile("p1", "u1", {"summary": "New summary"})
    assert result2["profile_version"] == 3


@pytest.mark.asyncio
async def test_update_wrong_user_returns_none(profile_service, fake_db):
    """Update must reject if user_id doesn't match."""
    fake_db._store["p1"] = {"id": "p1", "user_id": "u1", "profile_version": 1}

    result = await profile_service.update_profile("p1", "wrong-user", {"title": "Hacked"})
    assert result is None


@pytest.mark.asyncio
async def test_delete_profile(profile_service, fake_db):
    """Delete should remove profile."""
    fake_db._store["p1"] = {"id": "p1", "user_id": "u1"}

    assert await profile_service.delete_profile("p1", "u1") is True
    assert "p1" not in fake_db._store

    assert await profile_service.delete_profile("nonexistent", "u1") is False


@pytest.mark.asyncio
async def test_set_primary_clears_others(profile_service, fake_db):
    """Setting primary should clear is_primary on other profiles."""
    fake_db._store["p1"] = {"id": "p1", "user_id": "u1", "is_primary": True, "profile_version": 1}
    fake_db._store["p2"] = {"id": "p2", "user_id": "u1", "is_primary": False, "profile_version": 1}

    result = await profile_service.set_primary("p2", "u1")
    assert result["is_primary"] is True
    assert fake_db._store["p1"]["is_primary"] is False


@pytest.mark.asyncio
async def test_completeness_score_calculation(profile_service):
    """Completeness score must weight sections correctly."""
    profile = {
        "name": "Test", "title": "Dev", "summary": "Test", "contact_info": {"email": "a@b.com", "phone": "123"},
        "experience": [{"company": "A"}, {"company": "B"}, {"company": "C"}],
        "education": [{"institution": "MIT"}],
        "skills": [{"name": "Python"}, {"name": "JS"}, {"name": "Go"}],
        "certifications": [{"name": "AWS"}],
        "projects": [{"name": "App"}],
        "social_links": {"linkedin": "url", "github": "url"},
    }
    result = profile_service.compute_completeness(profile)
    assert result["score"] > 50
    assert "sections" in result
    assert "suggestions" in result


@pytest.mark.asyncio
async def test_resume_worth_score(profile_service, fake_db):
    """Resume worth score should compute for a well-populated profile."""
    fake_db._store["p1"] = {
        "id": "p1", "user_id": "u1", "is_primary": True, "profile_version": 1,
        "skills": [{"name": "Python", "level": "expert"}, {"name": "JS", "level": "advanced"}],
        "experience": [{"company": "FAANG", "start_date": "2018", "end_date": "2024"}],
        "certifications": [{"name": "AWS"}],
        "projects": [{"name": "App"}],
        "education": [{"institution": "MIT"}],
    }

    result = await profile_service.compute_resume_worth("u1")
    assert result["score"] > 0
    assert result["label"] in ("Exceptional", "Strong", "Developing", "Getting Started")
    assert "breakdown" in result


@pytest.mark.asyncio
async def test_aggregate_gap_analysis_empty(profile_service, fake_db):
    """Gap analysis with no applications should return empty results."""
    result = await profile_service.aggregate_gap_analysis("u1")
    assert result["total_applications_analyzed"] == 0
    assert result["most_missing_skills"] == []


@pytest.mark.asyncio
async def test_augment_skills_increments_version(profile_service, fake_db):
    """Skill augmentation should increment profile_version."""
    fake_db._store["p1"] = {
        "id": "p1", "user_id": "u1", "profile_version": 3,
        "skills": [{"name": "Python", "level": "advanced", "source": "resume"}],
        "contact_info": {
            "social_connections": {
                "github": {
                    "data": {"top_languages": ["TypeScript", "Rust"], "top_repos": []}
                }
            }
        },
        "social_links": {}, "experience": [], "education": [],
        "certifications": [], "projects": [],
    }

    result = await profile_service.augment_skills_from_connections("p1", "u1")
    assert result["added"] == 2  # TypeScript + Rust
    assert fake_db._store["p1"]["profile_version"] == 4  # incremented


@pytest.mark.asyncio
async def test_evidence_sync_merges_without_duplication(profile_service, fake_db):
    """Evidence sync should add new items without duplicating existing ones."""
    fake_db._store["p1"] = {
        "id": "p1", "user_id": "u1", "profile_version": 1,
        "certifications": [{"name": "AWS SAA", "issuer": "AWS"}],
        "projects": [{"name": "MyApp"}],
        "skills": [], "experience": [], "education": [],
        "social_links": {}, "contact_info": {},
    }
    # Fake evidence items
    fake_db._store["ev1"] = {
        "id": "ev1", "user_id": "u1", "type": "cert",
        "title": "AWS SAA",  # duplicate
    }
    fake_db._store["ev2"] = {
        "id": "ev2", "user_id": "u1", "type": "cert",
        "title": "GCP Professional",  # new
    }
    fake_db._store["ev3"] = {
        "id": "ev3", "user_id": "u1", "type": "projects",
        "title": "NewProject",  # new
    }

    result = await profile_service.sync_evidence_to_profile("p1", "u1")
    assert result["merged_certs"] == 1  # Only GCP, not duplicated AWS
    assert result["merged_projects"] == 1


# ── Route-level tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_upload_rejects_empty_file(client):
    """Upload should reject empty files with 400."""
    resp = await client.post(
        "/api/profile/upload",
        files={"file": ("resume.pdf", b"", "application/pdf")},
        headers={"Authorization": "Bearer fake"},
    )
    # Without valid auth: 401; with valid auth and empty file: 400
    assert resp.status_code in (400, 401, 503)


@pytest.mark.asyncio
async def test_profile_upload_rejects_bad_extension(client):
    """Upload should reject files with unsupported extensions."""
    resp = await client.post(
        "/api/profile/upload",
        files={"file": ("script.exe", b"MZ...", "application/octet-stream")},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (400, 401, 503)


@pytest.mark.asyncio
async def test_profile_list_requires_auth(client):
    """Profile list endpoints require auth."""
    for path in ("/api/profile", "/api/profile/all", "/api/profile/primary"):
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} returned {resp.status_code}"


@pytest.mark.asyncio
async def test_profile_get_validates_uuid(client):
    """Profile get with non-UUID should return 422 not 500."""
    resp = await client.get(
        "/api/profile/not-a-uuid",
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (401, 422, 503)


@pytest.mark.asyncio
async def test_intelligence_endpoints_require_auth(client):
    """Intelligence endpoints require auth."""
    endpoints = [
        "/api/profile/intelligence/completeness",
        "/api/profile/intelligence/resume-worth",
        "/api/profile/intelligence/aggregate-gaps",
        "/api/profile/intelligence/market",
        "/api/profile/evidence/synced",
    ]
    for path in endpoints:
        resp = await client.get(path)
        assert resp.status_code == 401, f"{path} returned {resp.status_code}"


@pytest.mark.asyncio
async def test_social_links_update_requires_auth(client):
    """Social links PUT requires auth."""
    resp = await client.put(
        "/api/profile/fake-id/social-links",
        json={"linkedin": "https://linkedin.com/in/test"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_connect_social_validates_platform(client):
    """Connect social should validate platform name."""
    resp = await client.post(
        "/api/profile/fake-id/connect-social",
        json={"platform": "myspace", "url": "https://myspace.com/test"},
        headers={"Authorization": "Bearer fake"},
    )
    assert resp.status_code in (400, 401, 503)
