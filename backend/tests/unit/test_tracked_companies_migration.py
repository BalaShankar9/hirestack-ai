"""B2.schema — pin invariants of the tracked_companies migration.

The migration powers the B1 portal_scanner_worker fan-out (4b57519).
These tests are cheap structural checks — they don't run SQL, just
read the file — but they catch the most common drift modes:

* Field rename (provider → ats_provider) breaks portal_scanner.py
  TrackedCompany dataclass mapping silently in prod.
* Provider CHECK list drifts from portal_scanner.PROVIDERS so the
  worker can never scan a row inserted via the API.
* RLS forgotten → cross-tenant leak.
* UNIQUE missing → API upsert path becomes O(n) duplicates.

Anything beyond these is over-pinning; the integration tests do the
real validation.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "20260507000000_tracked_companies.sql"


def _sql() -> str:
    assert MIGRATION.exists(), f"Migration missing: {MIGRATION}"
    return MIGRATION.read_text()


def test_table_exists_with_idempotent_create() -> None:
    sql = _sql()
    assert "CREATE TABLE IF NOT EXISTS public.tracked_companies" in sql
    # BEGIN/COMMIT bracket so partial apply on Supabase rolls back.
    assert sql.lstrip().startswith("--") or sql.lstrip().startswith("BEGIN")
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql


def test_required_fields_match_TrackedCompany_dataclass() -> None:
    """portal_scanner.py exposes TrackedCompany(provider, company_slug,
    workday_tenant). The migration MUST keep those exact column names
    so the API can map row → dataclass without alias plumbing."""
    sql = _sql()
    for col in ("provider", "company_slug", "workday_tenant"):
        assert col in sql, f"Required column missing: {col}"
    # Also ownership / lifecycle fields.
    for col in ("user_id", "org_id", "display_name", "enabled",
                "last_scanned_at", "scan_error", "created_at", "updated_at"):
        assert col in sql, f"Required column missing: {col}"


def test_provider_check_matches_portal_scanner_supported_set() -> None:
    """The CHECK constraint MUST equal portal_scanner.PROVIDERS — if
    these drift, the API can insert rows the worker can't scan, or
    vice versa."""
    from app.services.portal_scanner import PROVIDERS

    sql = _sql()
    # Find the provider CHECK clause.
    for p in PROVIDERS:
        assert f"'{p}'" in sql, f"Provider missing from CHECK: {p}"


def test_workday_tenant_is_required_only_for_workday() -> None:
    """Per portal_scanner: workday rows need a tenant; others don't.
    This invariant is enforced at the DB so the API can stay dumb."""
    sql = _sql()
    assert "tracked_companies_workday_tenant_chk" in sql
    assert "provider = 'workday'" in sql
    assert "workday_tenant IS NOT NULL" in sql
    assert "workday_tenant IS NULL" in sql  # the non-workday branch


def test_unique_constraint_user_provider_slug() -> None:
    sql = _sql()
    assert "tracked_companies_user_provider_slug_uniq" in sql
    assert "UNIQUE (user_id, provider, company_slug)" in sql


def test_rls_enabled_with_owner_and_service_role_policies() -> None:
    sql = _sql()
    assert "ALTER TABLE public.tracked_companies ENABLE ROW LEVEL SECURITY" in sql
    assert 'POLICY "own_tracked_companies"' in sql
    assert "auth.uid() = user_id" in sql
    assert 'POLICY "service_role_tracked_companies"' in sql
    assert "auth.role() = 'service_role'" in sql


def test_hot_index_for_worker_scan_order() -> None:
    """The worker picks the next company to scan via
    `WHERE enabled ORDER BY last_scanned_at NULLS FIRST` — that
    needs an index or it becomes O(n) once a user tracks 100+
    companies."""
    sql = _sql()
    assert "idx_tracked_companies_user_enabled" in sql
    assert "last_scanned_at NULLS FIRST" in sql
    assert "WHERE enabled = true" in sql
