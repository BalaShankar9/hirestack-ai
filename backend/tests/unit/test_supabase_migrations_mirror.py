"""S2-F1/F2: pin supabase/migrations as the source of truth.

`supabase/migrations/` is what `supabase db push` deploys, and as of
m9-pr33 (M10) it is the *only* migration root in the repo. The legacy
`database/migrations/` directory has been deleted.

These regression tests pin three invariants:

1. The Stripe webhook idempotency table migration exists in
   `supabase/migrations/`. (Fix for the orphan found in the S2 audit.)
2. `processed_webhook_events` is created in supabase/ and the
   primary key on event_id is preserved.
3. The legacy `database/migrations/` directory MUST NOT come back —
   the single-root invariant is enforced statically.
4. Every public table created in `supabase/migrations/` has RLS
   enabled (S2-F3 defence-in-depth).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SUPABASE_DIR = REPO_ROOT / "supabase" / "migrations"


def test_stripe_webhook_idempotency_in_supabase_migrations() -> None:
    matches = list(SUPABASE_DIR.glob("*_stripe_webhook_idempotency.sql"))
    assert matches, (
        "Stripe webhook idempotency migration must live in "
        "supabase/migrations/ — production deploys read from there."
    )
    sql = matches[0].read_text()
    assert "processed_webhook_events" in sql
    # PRIMARY KEY on event_id is the actual idempotency lock.
    assert "PRIMARY KEY" in sql
    assert "event_id" in sql
    # Service-role-only table — must be deny-by-default for anon /
    # authenticated. RLS enabled with zero policies achieves that.
    assert "ENABLE ROW LEVEL SECURITY" in sql


def test_legacy_database_migrations_dir_does_not_exist() -> None:
    """m9-pr33 (M10) consolidated to a single migration root. The legacy
    `database/migrations/` directory was the orphan trap that caused the
    S2 schema-drift incident; deleting it removes the trap entirely.
    Resurrecting that directory would re-open the orphan trap."""
    legacy_dir = REPO_ROOT / "database" / "migrations"
    assert not legacy_dir.exists(), (
        "`database/migrations/` was deleted by m9-pr33. Do not recreate it. "
        "All schema changes belong in `supabase/migrations/` only."
    )


# ── S2-F3: every public table must have RLS enabled ──────────────────

# Tables that are intentionally not RLS-protected. Keep this list TINY;
# every entry needs a justification comment and a pointer to the migration
# that defines the table.
RLS_ALLOWLIST: dict[str, str] = {
    # No exemptions today. Add only with a reviewed justification.
}


def _table_re() -> "re.Pattern[str]":
    return re.compile(
        r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-z_][a-z0-9_]*)",
        re.IGNORECASE | re.MULTILINE,
    )


def _rls_re() -> "re.Pattern[str]":
    return re.compile(
        r"ALTER\s+TABLE\s+(?:public\.)?([a-z_][a-z0-9_]*)\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        re.IGNORECASE,
    )


def test_every_public_table_has_rls_enabled() -> None:
    """Defence-in-depth: every table created in supabase/migrations/
    must have RLS enabled somewhere in supabase/migrations/.

    The S2 audit found `ai_platform_spend_daily` was the lone gap;
    20260428000000_rls_backstop_platform_spend.sql closes it. This
    test prevents future tables from shipping without RLS.
    """
    table_re = _table_re()
    rls_re = _rls_re()

    declared: set[str] = set()
    rls_enabled: set[str] = set()

    for path in SUPABASE_DIR.glob("*.sql"):
        text = path.read_text()
        declared.update(m.group(1).lower() for m in table_re.finditer(text))
        rls_enabled.update(m.group(1).lower() for m in rls_re.finditer(text))

    missing = sorted(
        t for t in declared if t not in rls_enabled and t not in RLS_ALLOWLIST
    )

    assert not missing, (
        "These tables in supabase/migrations/ have no `ENABLE ROW LEVEL SECURITY` "
        "statement. Add RLS or justify in RLS_ALLOWLIST: "
        f"{missing}"
    )
