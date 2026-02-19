#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v supabase >/dev/null 2>&1; then
  echo "Error: supabase CLI not found on PATH" >&2
  exit 1
fi

STATUS_ENV="$(
  cd "$ROOT_DIR/supabase"
  supabase status -o env 2>/dev/null || true
)"

get_val() {
  local key="$1"
  # Grab the last matching line to tolerate any extra "Using workdir" output.
  echo "$STATUS_ENV" | awk -F= -v k="$key" '$1==k {print substr($0, index($0,"=")+1)}' | tail -n 1 | tr -d '"'
}

API_URL="$(get_val API_URL)"

# By default we keep Supabase's API_URL as-is (usually http://127.0.0.1:54321).
# Note: On some machines, "localhost" resolves to IPv6 (::1) and can break
# Realtime websockets in Firefox. If you need to force localhost anyway, set:
#   HIRESTACK_SUPABASE_HOST=localhost ./scripts/dev/sync_supabase_env.sh
if [[ "${HIRESTACK_SUPABASE_HOST:-}" == "localhost" ]]; then
  API_URL="${API_URL/127.0.0.1/localhost}"
elif [[ "${HIRESTACK_SUPABASE_HOST:-}" == "127.0.0.1" ]]; then
  API_URL="${API_URL/localhost/127.0.0.1}"
fi
ANON_KEY="$(get_val ANON_KEY)"
SERVICE_ROLE_KEY="$(get_val SERVICE_ROLE_KEY)"
JWT_SECRET="$(get_val JWT_SECRET)"

if [[ -z "${API_URL:-}" || -z "${ANON_KEY:-}" || -z "${SERVICE_ROLE_KEY:-}" || -z "${JWT_SECRET:-}" ]]; then
  echo "Error: could not read Supabase local status. Is 'supabase start' running?" >&2
  exit 1
fi

# Backend API base URL consumed by the Next.js frontend.
# Use 127.0.0.1 by default to avoid IPv6 "localhost" quirks in some browsers.
API_BASE_URL="${HIRESTACK_API_URL:-http://127.0.0.1:8000}"

FRONT_ENV="$ROOT_DIR/frontend/.env.local"
BACK_ENV="$ROOT_DIR/backend/.env"

if [[ ! -f "$BACK_ENV" ]]; then
  cp "$ROOT_DIR/backend/.env.example" "$BACK_ENV"
  echo "Created backend/.env from backend/.env.example"
fi

chmod 600 "$BACK_ENV" 2>/dev/null || true

if [[ ! -f "$FRONT_ENV" ]]; then
  cp "$ROOT_DIR/frontend/.env.example" "$FRONT_ENV"
  echo "Created frontend/.env.local from frontend/.env.example"
fi

export ENV_FILE_BACK="$BACK_ENV"
export ENV_FILE_FRONT="$FRONT_ENV"
export NEW_SUPABASE_URL="$API_URL"
export NEW_SUPABASE_ANON_KEY="$ANON_KEY"
export NEW_SUPABASE_SERVICE_ROLE_KEY="$SERVICE_ROLE_KEY"
export NEW_SUPABASE_JWT_SECRET="$JWT_SECRET"
export NEW_API_BASE_URL="$API_BASE_URL"

python3 - <<'PY'
import os
import re
from pathlib import Path

def upsert(path: Path, updates: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = text.splitlines()

    def upsert_one(lines: list[str], key: str, value: str) -> list[str]:
        pattern = re.compile(rf"^{re.escape(key)}=")
        out: list[str] = []
        replaced = False
        for line in lines:
            if pattern.match(line):
                out.append(f"{key}={value}")
                replaced = True
            else:
                out.append(line)
        if not replaced:
            if out and out[-1].strip() != "":
                out.append("")
            out.append(f"{key}={value}")
        return out

    for k, v in updates.items():
        lines = upsert_one(lines, k, v)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

back = Path(os.environ["ENV_FILE_BACK"])
front = Path(os.environ["ENV_FILE_FRONT"])

api_url = os.environ["NEW_SUPABASE_URL"]
anon = os.environ["NEW_SUPABASE_ANON_KEY"]
service = os.environ["NEW_SUPABASE_SERVICE_ROLE_KEY"]
jwt = os.environ["NEW_SUPABASE_JWT_SECRET"]

upsert(back, {
    "SUPABASE_URL": api_url,
    "SUPABASE_ANON_KEY": anon,
    "SUPABASE_SERVICE_ROLE_KEY": service,
    "SUPABASE_JWT_SECRET": jwt,
})

upsert(front, {
    "NEXT_PUBLIC_SUPABASE_URL": api_url,
    "NEXT_PUBLIC_SUPABASE_ANON_KEY": anon,
    "NEXT_PUBLIC_API_URL": os.environ["NEW_API_BASE_URL"],
})
PY

unset NEW_SUPABASE_ANON_KEY NEW_SUPABASE_SERVICE_ROLE_KEY NEW_SUPABASE_JWT_SECRET

echo "Synced Supabase env vars to backend/.env and frontend/.env.local."
