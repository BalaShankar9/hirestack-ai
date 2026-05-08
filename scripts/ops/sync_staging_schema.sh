#!/usr/bin/env bash
# m11-pr45: Schema-only sync from prod → staging.
#
# Snapshots the prod Postgres schema with ``pg_dump --schema-only``
# and applies it to the staging database. Carries NO row data —
# staging gets the prod *shape* but its own seed data. Idempotent;
# can be re-run safely (uses ``--clean --if-exists`` so the staging
# schema is dropped + recreated atomically inside one transaction).
#
# Required env:
#   PROD_DATABASE_URL    — read-only postgres URL to prod
#   STAGING_DATABASE_URL — read/write postgres URL to staging
#
# Optional env:
#   SCHEMAS    — comma-separated list (default: "public")
#   DRY_RUN    — "1" to print the dump path and skip the apply step
#   DUMP_DIR   — where to keep the dump (default: /tmp)
#
# Exit codes:
#   0 — success
#   1 — missing required env / bad input
#   2 — pg_dump failed
#   3 — psql apply failed
set -euo pipefail

if [[ -z "${PROD_DATABASE_URL:-}" ]]; then
  echo "ERROR: PROD_DATABASE_URL is not set" >&2
  exit 1
fi
if [[ -z "${STAGING_DATABASE_URL:-}" ]]; then
  echo "ERROR: STAGING_DATABASE_URL is not set" >&2
  exit 1
fi

SCHEMAS="${SCHEMAS:-public}"
DUMP_DIR="${DUMP_DIR:-/tmp}"
DRY_RUN="${DRY_RUN:-0}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DUMP_PATH="${DUMP_DIR}/hirestack-prod-schema-${TIMESTAMP}.sql"

echo "[$(date -u +%H:%M:%S)] dumping prod schema (schemas=${SCHEMAS}) → ${DUMP_PATH}"

# Build --schema flags from comma-separated list.
SCHEMA_FLAGS=()
IFS=',' read -ra SCHEMA_LIST <<< "${SCHEMAS}"
for s in "${SCHEMA_LIST[@]}"; do
  SCHEMA_FLAGS+=("--schema=${s}")
done

# --schema-only        → no row data
# --clean --if-exists  → emit DROP statements before CREATE so a re-run
#                        atomically replaces existing objects
# --no-owner           → strip OWNER TO clauses (staging may use a
#                        different role than prod)
# --no-privileges      → strip GRANT/REVOKE (staging RBAC is independent)
# --no-tablespaces     → strip TABLESPACE clauses (staging may not have
#                        the same tablespace names)
if ! pg_dump \
  --schema-only \
  --clean --if-exists \
  --no-owner \
  --no-privileges \
  --no-tablespaces \
  "${SCHEMA_FLAGS[@]}" \
  --file="${DUMP_PATH}" \
  "${PROD_DATABASE_URL}"; then
  echo "ERROR: pg_dump failed" >&2
  exit 2
fi

DUMP_SIZE_KB=$(( $(wc -c < "${DUMP_PATH}") / 1024 ))
echo "[$(date -u +%H:%M:%S)] dump complete: ${DUMP_SIZE_KB} KiB"

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "DRY_RUN=1 — dump saved at ${DUMP_PATH}, NOT applying to staging"
  exit 0
fi

# Apply inside a single transaction with ON_ERROR_STOP so a partial
# failure doesn't leave staging in a half-migrated state.
echo "[$(date -u +%H:%M:%S)] applying dump to staging"
if ! psql \
  --single-transaction \
  --variable=ON_ERROR_STOP=1 \
  --quiet \
  --file="${DUMP_PATH}" \
  "${STAGING_DATABASE_URL}"; then
  echo "ERROR: psql apply failed; staging schema unchanged (rolled back)" >&2
  exit 3
fi

echo "[$(date -u +%H:%M:%S)] staging schema sync complete"
