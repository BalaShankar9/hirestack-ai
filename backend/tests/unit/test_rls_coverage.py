"""S2-F3: pin RLS coverage on every public table.

If a migration ever adds a CREATE TABLE without an
`ALTER TABLE … ENABLE ROW LEVEL SECURITY`, this test fails. That
forces the author to either (a) enable RLS, or (b) explicitly
add the table name to the allowlist with a justification.

Why allowlist instead of guess-by-column-name: tables like
`ai_platform_spend_daily` have no user_id but are still sensitive
(cost data); a naive heuristic would miss them.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SUPABASE_DIR = REPO_ROOT / "supabase" / "migrations"

# Tables that legitimately do NOT need RLS. Add with a comment
# explaining why — every entry here is a security decision.
RLS_EXEMPT: dict[str, str] = {
    # No public tables are exempt today. Keep this dict so future
    # additions are explicit.
}


def _scan() -> tuple[set[str], set[str], dict[str, str]]:
    tables: dict[str, str] = {}
    rls: set[str] = set()
    create_re = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?"
        r"([a-zA-Z_][a-zA-Z_0-9]*)\s*\(",
        re.IGNORECASE,
    )
    rls_re = re.compile(
        r"ALTER\s+TABLE\s+(?:public\.)?([a-zA-Z_][a-zA-Z_0-9]*)\s+"
        r"ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        re.IGNORECASE,
    )
    for path in sorted(SUPABASE_DIR.glob("*.sql")):
        text = path.read_text()
        for m in create_re.finditer(text):
            tables.setdefault(m.group(1).lower(), path.name)
        for m in rls_re.finditer(text):
            rls.add(m.group(1).lower())
    return set(tables), rls, tables


def test_every_public_table_has_rls_enabled() -> None:
    table_names, rls, source = _scan()
    missing = sorted(
        n for n in table_names if n not in rls and n not in RLS_EXEMPT
    )
    assert not missing, (
        "Every public table must ENABLE ROW LEVEL SECURITY. "
        "Add an `ALTER TABLE … ENABLE ROW LEVEL SECURITY;` to the "
        "originating migration, or add the name to RLS_EXEMPT in "
        f"this test with a written justification. Missing: "
        + ", ".join(f"{n} [{source[n]}]" for n in missing)
    )


def test_rls_enabled_only_on_known_tables() -> None:
    """Sanity: every RLS ALTER targets a table we actually create."""
    table_names, rls, _ = _scan()
    orphan = sorted(rls - table_names)
    assert not orphan, (
        "RLS enabled on tables that aren't defined in supabase/migrations/. "
        "Either the table moved or the ALTER is stale: " + ", ".join(orphan)
    )
