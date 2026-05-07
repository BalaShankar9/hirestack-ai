#!/usr/bin/env bash
# PR m4-pr13: regenerate the typed SDK from the running backend's OpenAPI spec.
#
# Usage:
#   tools/codegen/openapi.sh                 # uses BACKEND_URL or http://localhost:8000
#   BACKEND_URL=https://staging tools/codegen/openapi.sh
#
# CI invariant: after running, `git diff --exit-code frontend/src/lib/sdk/` must
# be empty. Drift = a backend route changed shape without the SDK being
# regenerated.
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
OUT_DIR="frontend/src/lib/sdk"
SCHEMA_FILE="${OUT_DIR}/schema.d.ts"
SPEC_TMP="${OUT_DIR}/.openapi.tmp.json"

mkdir -p "${OUT_DIR}"

echo "[openapi] fetching ${BACKEND_URL}/openapi.json"
curl -fsSL "${BACKEND_URL}/openapi.json" -o "${SPEC_TMP}"

echo "[openapi] generating ${SCHEMA_FILE}"
npx --yes openapi-typescript "${SPEC_TMP}" -o "${SCHEMA_FILE}"

rm -f "${SPEC_TMP}"
echo "[openapi] done"
