from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SUPABASE_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations" / "20260509000000_missions_and_drafts.sql"
)
DATABASE_MIGRATION = (
    REPO_ROOT / "database" / "migrations" / "20260509_missions_and_drafts.sql"
)


def _sql() -> str:
    assert SUPABASE_MIGRATION.exists(), f"Migration missing: {SUPABASE_MIGRATION}"
    assert DATABASE_MIGRATION.exists(), f"Mirror migration missing: {DATABASE_MIGRATION}"
    return SUPABASE_MIGRATION.read_text()


def test_migration_is_transaction_wrapped() -> None:
    sql = _sql()
    assert sql.lstrip().startswith("--") or sql.lstrip().startswith("BEGIN")
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql


def test_applications_status_adds_evaluated() -> None:
    sql = _sql()
    assert "ALTER TABLE public.applications" in sql
    assert "chk_applications_status" in sql
    assert "'evaluated'" in sql


def test_missions_table_has_required_fields_and_checks() -> None:
    sql = _sql()
    assert "CREATE TABLE IF NOT EXISTS public.missions" in sql
    for column in (
        "user_id",
        "name",
        "status",
        "role_titles",
        "locations",
        "comp_band_min",
        "comp_band_max",
        "must_haves",
        "deal_breakers",
        "min_fit_score",
        "target_volume_per_week",
        "voice_preset",
        "created_at",
        "paused_at",
    ):
        assert column in sql, f"Missing missions column: {column}"
    for token in (
        "missions_status_chk",
        "missions_min_fit_score_chk",
        "missions_target_volume_chk",
        "missions_comp_band_chk",
        "missions_voice_preset_chk",
        "'confident_selective'",
        "'warm_eager'",
        "'formal_traditional'",
    ):
        assert token in sql


def test_mission_drafts_table_has_required_fields_and_constraints() -> None:
    sql = _sql()
    assert "CREATE TABLE IF NOT EXISTS public.mission_drafts" in sql
    for column in (
        "mission_id",
        "application_id",
        "surfaced_at",
        "prepared_at",
        "sent_at",
        "status",
        "fit_score",
    ):
        assert column in sql, f"Missing mission_drafts column: {column}"
    for token in (
        "mission_drafts_status_chk",
        "mission_drafts_fit_score_chk",
        "mission_drafts_mission_application_uniq",
        "UNIQUE (mission_id, application_id)",
        "'ready_for_user'",
    ):
        assert token in sql


def test_rls_and_indexes_exist_for_both_tables() -> None:
    sql = _sql()
    for token in (
        "ALTER TABLE public.missions ENABLE ROW LEVEL SECURITY",
        'POLICY "own_missions"',
        'POLICY "service_role_missions"',
        "idx_missions_user_status_created",
        "ALTER TABLE public.mission_drafts ENABLE ROW LEVEL SECURITY",
        'POLICY "own_mission_drafts"',
        'POLICY "service_role_mission_drafts"',
        "idx_mission_drafts_mission_status_surfaced",
    ):
        assert token in sql