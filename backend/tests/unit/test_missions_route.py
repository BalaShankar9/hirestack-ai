from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.api import deps as api_deps
from app.api.routes import missions as missions_route
from app.api.routes.missions import get_db_dep


_FAKE_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "u@example.com",
}
_OTHER_USER = {
    "id": "00000000-0000-0000-0000-000000000002",
    "email": "other@example.com",
}


class _FakeDB:
    def __init__(self) -> None:
        self.missions: dict[str, dict] = {}
        self.drafts: dict[str, dict] = {}
        self.applications: dict[str, dict] = {}
        self._counter = 0
        self._draft_counter = 0
        self._application_counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"00000000-0000-0000-0001-{self._counter:012d}"

    def _next_draft_id(self) -> str:
        self._draft_counter += 1
        return f"00000000-0000-0000-0002-{self._draft_counter:012d}"

    def _next_application_id(self) -> str:
        self._application_counter += 1
        return f"00000000-0000-0000-0003-{self._application_counter:012d}"

    async def create(self, table, data, doc_id=None):
        if table == missions_route.TABLES["missions"]:
            new_id = doc_id or self._next_id()
            stored = {**data, "id": new_id}
            stored.setdefault("created_at", "2026-05-09T00:00:00+00:00")
            self.missions[new_id] = stored
            return new_id
        if table == missions_route.TABLES["mission_drafts"]:
            for row in self.drafts.values():
                if (
                    row["mission_id"] == data["mission_id"]
                    and row.get("application_id")
                    and row.get("application_id") == data.get("application_id")
                ):
                    raise Exception("duplicate key value violates unique constraint")
            new_id = doc_id or self._next_draft_id()
            stored = {**data, "id": new_id}
            stored.setdefault("surfaced_at", "2026-05-09T00:00:00+00:00")
            stored.setdefault("status", "surfaced")
            self.drafts[new_id] = stored
            return new_id
        if table == missions_route.TABLES["applications"]:
            new_id = doc_id or self._next_application_id()
            stored = {**data, "id": new_id}
            stored.setdefault("updated_at", "2026-05-09T00:00:00+00:00")
            self.applications[new_id] = stored
            return new_id
        raise AssertionError(f"Unexpected table: {table}")

    async def get(self, table, doc_id):
        if table == missions_route.TABLES["missions"]:
            return self.missions.get(doc_id)
        if table == missions_route.TABLES["mission_drafts"]:
            return self.drafts.get(doc_id)
        if table == missions_route.TABLES["applications"]:
            return self.applications.get(doc_id)
        return None

    async def update(self, table, doc_id, data):
        if table == missions_route.TABLES["missions"]:
            if doc_id not in self.missions:
                return False
            self.missions[doc_id] = {**self.missions[doc_id], **data}
            return True
        if table == missions_route.TABLES["mission_drafts"]:
            if doc_id not in self.drafts:
                return False
            self.drafts[doc_id] = {**self.drafts[doc_id], **data}
            return True
        if table == missions_route.TABLES["applications"]:
            if doc_id not in self.applications:
                return False
            self.applications[doc_id] = {**self.applications[doc_id], **data}
            return True
        return False

    async def delete(self, table, doc_id):
        if table == missions_route.TABLES["missions"]:
            deleted = self.missions.pop(doc_id, None)
            if not deleted:
                return False
            self.drafts = {
                key: value
                for key, value in self.drafts.items()
                if value.get("mission_id") != doc_id
            }
            return True
        if table == missions_route.TABLES["mission_drafts"]:
            return self.drafts.pop(doc_id, None) is not None
        if table == missions_route.TABLES["applications"]:
            return self.applications.pop(doc_id, None) is not None
        return False

    async def query(
        self,
        table,
        filters=None,
        order_by=None,
        order_direction="DESCENDING",
        limit=None,
        offset=None,
    ):
        if table == missions_route.TABLES["missions"]:
            out = list(self.missions.values())
        elif table == missions_route.TABLES["mission_drafts"]:
            out = list(self.drafts.values())
        elif table == missions_route.TABLES["applications"]:
            out = list(self.applications.values())
        else:
            out = []
        for col, op, val in filters or []:
            if op == "==":
                out = [row for row in out if row.get(col) == val]
            elif op == "in":
                out = [row for row in out if row.get(col) in val]
        if order_by:
            out.sort(
                key=lambda row: row.get(order_by, ""),
                reverse=(order_direction == "DESCENDING"),
            )
        if limit is not None:
            out = out[:limit]
        return out


def _build_app(db: _FakeDB, user: dict) -> FastAPI:
    app = FastAPI()
    app.state.limiter = missions_route.limiter
    app.include_router(missions_route.router, prefix="/api")
    app.dependency_overrides[api_deps.get_current_user] = lambda: user
    app.dependency_overrides[get_db_dep] = lambda: db
    return app


@pytest.fixture()
def client_factory():
    def _factory(db: _FakeDB | None = None, user: dict = _FAKE_USER) -> TestClient:
        try:
            missions_route.limiter.reset()
        except Exception:
            pass
        return TestClient(_build_app(db or _FakeDB(), user))

    return _factory


class TestMissionRoutes:
    def test_create_mission_happy_path(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)

        resp = client.post(
            "/api/missions",
            json={
                "name": "  Staff Product Design  ",
                "role_titles": ["Staff Product Designer", "  Staff Product Designer  ", ""],
                "locations": ["Remote", "New York"],
                "must_haves": ["B2B SaaS", "Design systems"],
                "deal_breakers": ["In-office five days"],
                "min_fit_score": 4.2,
                "target_volume_per_week": 7,
                "voice_preset": "warm_eager",
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["user_id"] == _FAKE_USER["id"]
        assert body["name"] == "Staff Product Design"
        assert body["role_titles"] == ["Staff Product Designer"]
        assert body["voice_preset"] == "warm_eager"
        assert body["status"] == "active"

    def test_create_invalid_voice_preset_returns_422(self, client_factory) -> None:
        client = client_factory()
        resp = client.post(
            "/api/missions",
            json={"name": "Design", "voice_preset": "casual"},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["field"] == "voice_preset"

    def test_list_only_returns_callers_missions(self, client_factory) -> None:
        db = _FakeDB()
        client_a = client_factory(db, user=_FAKE_USER)
        client_b = client_factory(db, user=_OTHER_USER)
        client_a.post("/api/missions", json={"name": "Mission A"})
        client_b.post("/api/missions", json={"name": "Mission B"})

        resp = client_a.get("/api/missions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["items"][0]["name"] == "Mission A"

    def test_patch_status_paused_sets_paused_at(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        created = client.post("/api/missions", json={"name": "Mission A"}).json()

        resp = client.patch(
            f"/api/missions/{created['id']}",
            json={"status": "paused"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"
        assert resp.json()["paused_at"] is not None

    def test_delete_other_users_mission_is_404(self, client_factory) -> None:
        db = _FakeDB()
        owner_client = client_factory(db, user=_FAKE_USER)
        other_client = client_factory(db, user=_OTHER_USER)
        created = owner_client.post("/api/missions", json={"name": "Owner Mission"}).json()

        resp = other_client.delete(f"/api/missions/{created['id']}")
        assert resp.status_code == 404


class TestMissionDraftRoutes:
    def test_create_draft_for_owned_mission(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        mission = client.post("/api/missions", json={"name": "Mission A"}).json()
        db.applications["10000000-0000-0000-0000-000000000001"] = {
            "id": "10000000-0000-0000-0000-000000000001",
            "user_id": _FAKE_USER["id"],
            "title": "Staff Product Designer",
            "status": "draft",
            "updated_at": "2026-05-09T00:00:00+00:00",
            "confirmed_facts": {"company": "Acme", "jobTitle": "Staff Product Designer"},
            "scores": {"fit": 4.6},
        }

        resp = client.post(
            f"/api/missions/{mission['id']}/drafts",
            json={
                "application_id": "10000000-0000-0000-0000-000000000001",
                "status": "ready_for_user",
                "fit_score": 4.6,
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["mission_id"] == mission["id"]
        assert body["status"] == "ready_for_user"
        assert body["prepared_at"] is not None
        assert body["application"]["company_name"] == "Acme"
        assert body["application"]["role_title"] == "Staff Product Designer"

    def test_duplicate_application_in_same_mission_returns_409(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        mission = client.post("/api/missions", json={"name": "Mission A"}).json()
        payload = {
            "application_id": "10000000-0000-0000-0000-000000000001",
            "status": "surfaced",
        }

        first = client.post(f"/api/missions/{mission['id']}/drafts", json=payload)
        second = client.post(f"/api/missions/{mission['id']}/drafts", json=payload)
        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["detail"]["field"] == "application_id"

    def test_list_drafts_filters_by_status(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        mission = client.post("/api/missions", json={"name": "Mission A"}).json()
        app_one_id = "20000000-0000-0000-0000-000000000001"
        app_two_id = "20000000-0000-0000-0000-000000000002"
        db.applications[app_one_id] = {
            "id": app_one_id,
            "user_id": _FAKE_USER["id"],
            "title": "Role One",
            "status": "draft",
            "updated_at": "2026-05-09T00:00:00+00:00",
            "confirmed_facts": {"company": "Stripe", "jobTitle": "Role One"},
            "scores": {"fit": 4.2},
        }
        db.applications[app_two_id] = {
            "id": app_two_id,
            "user_id": _FAKE_USER["id"],
            "title": "Role Two",
            "status": "submitted",
            "updated_at": "2026-05-09T00:00:00+00:00",
            "confirmed_facts": {"company": "Acme", "jobTitle": "Role Two"},
            "scores": {"fit": 4.8},
        }
        client.post(
            f"/api/missions/{mission['id']}/drafts",
            json={"status": "surfaced", "application_id": app_one_id},
        )
        client.post(
            f"/api/missions/{mission['id']}/drafts",
            json={"status": "sent", "application_id": app_two_id},
        )

        resp = client.get(f"/api/missions/{mission['id']}/drafts?status=sent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert body["items"][0]["status"] == "sent"
        assert body["items"][0]["application"]["company_name"] == "Acme"

    def test_patch_draft_status_sent_sets_sent_at(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        mission = client.post("/api/missions", json={"name": "Mission A"}).json()
        app_id = "20000000-0000-0000-0000-000000000003"
        db.applications[app_id] = {
            "id": app_id,
            "user_id": _FAKE_USER["id"],
            "title": "Role One",
            "status": "draft",
            "updated_at": "2026-05-09T00:00:00+00:00",
            "confirmed_facts": {"company": "Stripe", "jobTitle": "Role One"},
            "scores": {"fit": 4.5},
        }
        draft = client.post(
            f"/api/missions/{mission['id']}/drafts",
            json={"status": "surfaced", "application_id": app_id},
        ).json()

        resp = client.patch(
            f"/api/missions/{mission['id']}/drafts/{draft['id']}",
            json={"status": "sent"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"
        assert resp.json()["sent_at"] is not None
        assert resp.json()["application"]["role_title"] == "Role One"

    def test_sync_creates_ready_for_user_draft_from_matching_application(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        mission = client.post(
            "/api/missions",
            json={
                "name": "Design Leadership",
                "role_titles": ["Staff Product Designer"],
                "min_fit_score": 4.0,
            },
        ).json()
        db.applications["20000000-0000-0000-0000-000000000004"] = {
            "id": "20000000-0000-0000-0000-000000000004",
            "user_id": _FAKE_USER["id"],
            "title": "Staff Product Designer",
            "status": "evaluated",
            "updated_at": "2026-05-09T09:00:00+00:00",
            "confirmed_facts": {
                "company": "Acme",
                "jobTitle": "Staff Product Designer",
                "source": "tracked_company_auto_prep",
                "jd_text": "Remote B2B SaaS design systems",
            },
            "scores": {"fit": 4.6},
            "cv_html": "<p>CV</p>",
            "cover_letter_html": "<p>CL</p>",
            "scorecard": {"overall": 88},
        }

        resp = client.post(f"/api/missions/{mission['id']}/sync")

        assert resp.status_code == 200
        assert resp.json()["created"] == 1
        assert resp.json()["matched_applications"] == 1

        list_resp = client.get(f"/api/missions/{mission['id']}/drafts")
        assert list_resp.status_code == 200
        body = list_resp.json()
        assert body["count"] == 1
        assert body["items"][0]["status"] == "ready_for_user"
        assert body["items"][0]["application"]["ready_to_apply"] is True
        assert body["items"][0]["application"]["company_name"] == "Acme"

    def test_sync_skips_below_fit_floor(self, client_factory) -> None:
        db = _FakeDB()
        client = client_factory(db)
        mission = client.post(
            "/api/missions",
            json={
                "name": "Design Leadership",
                "role_titles": ["Staff Product Designer"],
                "min_fit_score": 4.5,
            },
        ).json()
        db.applications["20000000-0000-0000-0000-000000000005"] = {
            "id": "20000000-0000-0000-0000-000000000005",
            "user_id": _FAKE_USER["id"],
            "title": "Staff Product Designer",
            "status": "draft",
            "updated_at": "2026-05-09T09:00:00+00:00",
            "confirmed_facts": {"company": "Acme", "jobTitle": "Staff Product Designer"},
            "scores": {"fit": 4.2},
        }

        resp = client.post(f"/api/missions/{mission['id']}/sync")

        assert resp.status_code == 200
        assert resp.json()["created"] == 0
        assert resp.json()["matched_applications"] == 0
        assert client.get(f"/api/missions/{mission['id']}/drafts").json()["count"] == 0

    def test_other_user_cannot_read_draft(self, client_factory) -> None:
        db = _FakeDB()
        owner_client = client_factory(db, user=_FAKE_USER)
        other_client = client_factory(db, user=_OTHER_USER)
        mission = owner_client.post("/api/missions", json={"name": "Mission A"}).json()
        draft = owner_client.post(
            f"/api/missions/{mission['id']}/drafts",
            json={"status": "surfaced"},
        ).json()

        resp = other_client.get(f"/api/missions/{mission['id']}/drafts/{draft['id']}")
        assert resp.status_code == 404