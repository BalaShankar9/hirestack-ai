"""Organization service tests."""
import pytest

from app.core.database import TABLES
from app.services.org import OrgService


class FakeOrgDB:
    """Capture org deletion cleanup calls."""

    def __init__(self):
        self.delete_where_calls = []
        self.delete_calls = []

    async def delete_where(self, table, filters=None):
        self.delete_where_calls.append((table, filters))
        return True

    async def delete(self, table, doc_id):
        self.delete_calls.append((table, doc_id))
        return True


@pytest.mark.asyncio
async def test_delete_org_removes_org_owned_rows_before_org():
    db = FakeOrgDB()
    service = OrgService(db=db)

    result = await service.delete_org("org-1")

    assert result is True
    assert db.delete_where_calls == [
        (TABLES["candidates"], [("org_id", "==", "org-1")]),
        (TABLES["usage_records"], [("org_id", "==", "org-1")]),
        (TABLES["audit_logs"], [("org_id", "==", "org-1")]),
        (TABLES["org_invitations"], [("org_id", "==", "org-1")]),
        (TABLES["webhooks"], [("org_id", "==", "org-1")]),
        (TABLES["subscriptions"], [("org_id", "==", "org-1")]),
        (TABLES["org_members"], [("org_id", "==", "org-1")]),
    ]
    assert db.delete_calls == [(TABLES["organizations"], "org-1")]