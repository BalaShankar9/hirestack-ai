#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/backend/.env"
EXAMPLE_FILE="$ROOT_DIR/backend/.env.example"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ ! -f "$EXAMPLE_FILE" ]]; then
    echo "Error: missing backend/.env.example" >&2
    exit 1
  fi
  cp "$EXAMPLE_FILE" "$ENV_FILE"
  echo "Created backend/.env from backend/.env.example"
fi

chmod 600 "$ENV_FILE" 2>/dev/null || true

printf "Paste GEMINI_API_KEY (input hidden): "
IFS= read -r -s GEMINI_KEY
echo

if [[ -z "${GEMINI_KEY// }" ]]; then
  echo "Error: no key entered" >&2
  exit 1
fi

if [[ "$GEMINI_KEY" != AIza* ]]; then
  echo "Warning: this doesn't look like a Google AI Studio key (expected prefix: AIza...). Continuing anyway." >&2
fi

ENV_FILE="$ENV_FILE" NEW_AI_PROVIDER="gemini" NEW_GEMINI_API_KEY="$GEMINI_KEY" python3 - <<'PY'
import os
import re
from pathlib import Path

env_path = Path(os.environ["ENV_FILE"])

updates = {
    "AI_PROVIDER": os.environ["NEW_AI_PROVIDER"],
    "GEMINI_API_KEY": os.environ["NEW_GEMINI_API_KEY"],
    # Make the API-key flow explicit (avoid accidental Vertex mode)
    "GEMINI_USE_VERTEXAI": "false",
}

text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
lines = text.splitlines()

def upsert(lines: list[str], key: str, value: str) -> list[str]:
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
    lines = upsert(lines, k, v)

env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

unset GEMINI_KEY
echo "Updated backend/.env with AI_PROVIDER=gemini and GEMINI_API_KEY."

echo
echo "Verifying Gemini credentials (real request, key not printed)..."
if python3 "$ROOT_DIR/scripts/dev/verify_gemini_key.py"; then
  echo "Gemini verification OK."
else
  echo "Gemini verification FAILED. Double-check your key (Google AI Studio keys usually start with 'AIza…') or switch to Vertex AI mode." >&2
  exit 1
fi
