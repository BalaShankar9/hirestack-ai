"""S2-F1/F2: pin supabase/migrations as the source of truth.

`supabase/migrations/` is what `supabase db push` deploys.
`database/migrations/` is a legacy mirror that nothing reads for prod.
A migration that lives only in `database/migrations/` is an orphan —
production never gets it.

These regression tests pin three invariants:

1. The Stripe webhook idempotency table migration exists in
   `supabase/migrations/`. (Fix for the orphan found in the S2 audit.)
2. `processed_webhook_events` is created in supabase/ and the
   primary key on event_id is preserved.
3. Every migration in `database/migrations/` whose timestamp prefix
   begins with 2026 has a counterpart in `supabase/migrations/`
   (timestamp may differ in length; we match by suffix slug).

The third pin is the cheap, durable check that prevents the next
schema-drift incident.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SUPABASE_DIR = REPO_ROOT / "supabase" / "migrations"
DATABASE_DIR = REPO_ROOT / "database" / "migrations"

# Filenames in database/migrations/ that pre-date the supabase format
# and were superseded by 20260206000000_full_schema.sql. Allowed to
# have no supabase/ counterpart.
LEGACY_PRE_SUPABASE = {
    "001_initial_schema.sql",
    "002_frontend_tables.sql",
    "003_add_ps_portfolio_columns.sql",
    "20250610_atomic_module_status.sql",
    "20250611_add_recovery_attempts.sql",
}


def _slug(filename: str) -> str:
    """Strip the leading timestamp digits + underscore so we can match
    `20260420_stripe_webhook_idempotency.sql` against
    `20260420000000_stripe_webhook_idempotency.sql`."""
    return re.sub(r"^\d+_", "", filename)


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


def test_database_migrations_2026_have_supabase_counterpart() -> None:
    """Every 2026+ migration in the legacy database/migrations/ folder
    must also exist in supabase/migrations/. Slug match (timestamp
    granularity may differ)."""
    supabase_slugs = {_slug(p.name) for p in SUPABASE_DIR.glob("*.sql")}

    orphans: list[str] = []
    for path in DATABASE_DIR.glob("*.sql"):
        if path.name in LEGACY_PRE_SUPABASE:
            continue
        if not path.name.startswith("2026"):
            continue
        if _slug(path.name) not in supabase_slugs:
            orphans.append(path.name)

    assert not orphans, (
        "Migrations only in database/migrations/ never deploy to prod via "
        "`supabase db push`. Mirror these into supabase/migrations/: "
        f"{orphans}"
    )
