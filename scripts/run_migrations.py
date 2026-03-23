#!/usr/bin/env python3
"""
HireStack AI — Database Migration Runner
Applies all pending migrations to the Supabase PostgreSQL database.

Usage:
  python scripts/run_migrations.py --db-password YOUR_DB_PASSWORD

Or set the DATABASE_URL environment variable:
  DATABASE_URL=postgresql://postgres:PASSWORD@db.cigdytublaotsiyjlsze.supabase.co:5432/postgres python scripts/run_migrations.py
"""
import os
import sys
import argparse
from pathlib import Path


def get_connection_string(password: str = "") -> str:
    """Build the PostgreSQL connection string."""
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        return db_url

    ref = "cigdytublaotsiyjlsze"
    host = f"db.{ref}.supabase.co"
    port = 5432
    user = "postgres"
    db = "postgres"

    if not password:
        password = os.getenv("SUPABASE_DB_PASSWORD", "")

    if not password:
        print("ERROR: Database password required.")
        print("  Option 1: python scripts/run_migrations.py --db-password YOUR_PASSWORD")
        print("  Option 2: Set DATABASE_URL environment variable")
        print("  Option 3: Set SUPABASE_DB_PASSWORD environment variable")
        print("\nFind your password in: Supabase Dashboard → Settings → Database → Connection string")
        sys.exit(1)

    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def run_migrations(conn_str: str):
    """Run the consolidated migration SQL."""
    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    migration_file = Path(__file__).parent.parent / "database" / "apply_all_pending.sql"
    if not migration_file.exists():
        print(f"ERROR: Migration file not found: {migration_file}")
        sys.exit(1)

    sql = migration_file.read_text()

    print(f"Connecting to database...")
    try:
        conn = psycopg2.connect(conn_str)
        conn.autocommit = True
        cursor = conn.cursor()

        print(f"Running migration ({len(sql)} bytes)...")

        # Split into individual statements and run each
        # This handles the DO $$ blocks correctly
        statements = []
        current = []
        in_dollar = False

        for line in sql.split("\n"):
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("--"):
                current.append(line)
                continue

            # Track $$ blocks
            if "$$" in stripped:
                in_dollar = not in_dollar

            current.append(line)

            # Statement ends with ; and we're not inside a $$ block
            if stripped.endswith(";") and not in_dollar:
                stmt = "\n".join(current).strip()
                if stmt and not all(l.strip().startswith("--") or not l.strip() for l in current):
                    statements.append(stmt)
                current = []

        # Add any remaining statement
        if current:
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)

        success = 0
        errors = 0

        for i, stmt in enumerate(statements):
            # Skip comment-only blocks
            lines = [l for l in stmt.split("\n") if l.strip() and not l.strip().startswith("--")]
            if not lines:
                continue

            try:
                cursor.execute(stmt)
                success += 1
                # Print progress for major statements
                first_line = lines[0].strip()[:80] if lines else ""
                if any(kw in first_line.upper() for kw in ["CREATE TABLE", "ALTER TABLE", "CREATE INDEX", "CREATE POLICY"]):
                    print(f"  ✓ {first_line}")
            except Exception as e:
                err_msg = str(e).strip()
                # Ignore "already exists" errors (idempotent)
                if "already exists" in err_msg:
                    success += 1
                else:
                    errors += 1
                    first_line = lines[0].strip()[:60] if lines else "unknown"
                    print(f"  ✗ {first_line}: {err_msg[:100]}")

        cursor.close()
        conn.close()

        print(f"\nMigration complete: {success} successful, {errors} errors")

        if errors == 0:
            print("✅ All migrations applied successfully!")
        else:
            print(f"⚠️  {errors} statements had errors (non-critical if 'already exists')")

    except psycopg2.OperationalError as e:
        print(f"ERROR: Could not connect to database: {e}")
        print("\nMake sure:")
        print("  1. The password is correct")
        print("  2. Your IP is allowed in Supabase Dashboard → Settings → Database → Network")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run HireStack AI database migrations")
    parser.add_argument("--db-password", "-p", help="Supabase database password")
    parser.add_argument("--db-url", help="Full PostgreSQL connection URL")
    args = parser.parse_args()

    if args.db_url:
        conn_str = args.db_url
    else:
        conn_str = get_connection_string(args.db_password or "")

    run_migrations(conn_str)
