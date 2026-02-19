#!/usr/bin/env python3
"""
Verify Gemini credentials (Google AI Studio API key OR Vertex AI OAuth) for local dev.

This script:
- Reads config from backend/.env via backend/app/core/config.py
- Performs a tiny real request to confirm auth works
- Never prints the API key
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))


async def main() -> int:
    from backend.app.core.config import settings

    try:
        from google import genai
        from google.genai import types
    except Exception as e:
        print(f"ERROR: google-genai is not installed or failed to import: {e}")
        return 2

    model = settings.gemini_model

    try:
        if settings.gemini_use_vertexai:
            project = (settings.gemini_vertex_project or "").strip()
            location = (settings.gemini_vertex_location or "").strip()
            if not project or not location:
                print(
                    "ERROR: GEMINI_USE_VERTEXAI=true but GEMINI_VERTEX_PROJECT/"
                    "GEMINI_VERTEX_LOCATION are missing."
                )
                return 2

            client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
            mode = f"vertexai (project={project}, location={location})"
        else:
            key = (settings.gemini_api_key or "").strip()
            if not key:
                print("ERROR: GEMINI_API_KEY is empty.")
                return 2
            if not key.startswith("AIza"):
                print(
                    "WARNING: GEMINI_API_KEY does not match the typical Google AI Studio key "
                    "prefix ('AIza…'). Attempting a real request anyway."
                )

            client = genai.Client(api_key=key, vertexai=False)
            mode = "google ai studio api key"

        modality = getattr(types, "MediaModality", None) or getattr(types, "Modality", None)
        config_kwargs = {
            # Some Gemini models spend tokens in "thinking"; keep enough budget
            # (or disable thoughts) so we always get visible output.
            "max_output_tokens": 64,
            "temperature": 0,
        }
        if modality is not None:
            config_kwargs["response_modalities"] = [modality.TEXT]

        thinking_cfg = None
        if hasattr(types, "ThinkingConfig"):
            try:
                fields = getattr(types.ThinkingConfig, "model_fields", None)
                if fields and "thinking_budget" in fields:
                    thinking_cfg = types.ThinkingConfig(thinking_budget=0)
                else:
                    thinking_cfg = types.ThinkingConfig(include_thoughts=False)
            except Exception:
                thinking_cfg = None

        if thinking_cfg is not None:
            config_kwargs["thinking_config"] = thinking_cfg

        resp = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents="Reply with a single word: ok",
            config=types.GenerateContentConfig(**config_kwargs),
        )

        text = (resp.text or "").strip()
        if not text:
            print(f"ERROR: Gemini call returned empty text (mode={mode}, model={model}).")
            return 1

        print(f"OK: Gemini auth works (mode={mode}, model={model}). Response: {text!r}")
        return 0
    except Exception as e:
        msg = str(e).replace("\n", " ")
        print(f"ERROR: Gemini auth failed (mode={mode}, model={model}): {type(e).__name__}: {msg}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
