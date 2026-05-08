"""JSON Schema registry for domain events (m7-pr31, ADR-0035).

Lazily loads JSON Schema (Draft 2020-12) files from
``packages/events/schema/v1/`` and caches one ``Draft202012Validator`` per
``(event_type, event_version)`` pair for the lifetime of the process.

The registry is intentionally filesystem-only — schema files are resolved
by string format (``<event_type>.v<event_version>.schema.json``), not by
``$id`` introspection. This keeps the contract human-greppable.

Used by :class:`OutboxWriter` to gate ``append`` against
``ff_strict_event_validation`` (ADR-0035 §2). Ships in shadow mode by
default; flipping the flag promotes validation failures from log lines to
exceptions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# Resolve to <repo_root>/packages/events/schema/v1
_DEFAULT_SCHEMA_DIR = (
    Path(__file__).resolve().parents[4] / "packages" / "events" / "schema" / "v1"
)


class EventValidationError(Exception):
    """Envelope payload did not conform to its registered JSON Schema."""

    def __init__(self, event_type: str, event_version: int, errors: list[str]) -> None:
        self.event_type = event_type
        self.event_version = event_version
        self.errors = errors
        super().__init__(
            f"event {event_type} v{event_version} failed validation: "
            + "; ".join(errors)
        )


class MissingEventSchema(EventValidationError):
    """No schema file found for ``(event_type, event_version)``."""

    def __init__(self, event_type: str, event_version: int, path: Path) -> None:
        self._path = path
        super().__init__(
            event_type,
            event_version,
            [f"no schema file at {path}"],
        )


@dataclass
class _SchemaRegistry:
    """Lazy filesystem-backed JSON Schema cache."""

    schema_dir: Path = _DEFAULT_SCHEMA_DIR
    _validators: dict[tuple[str, int], Any] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def get_validator(self, event_type: str, event_version: int) -> Any:
        """Return a cached ``Draft202012Validator`` for ``(event_type, version)``.

        Raises:
            MissingEventSchema: if the schema file does not exist.
            RuntimeError: if the ``jsonschema`` package is not installed.
        """
        key = (event_type, event_version)
        cached = self._validators.get(key)
        if cached is not None:
            return cached

        with self._lock:
            cached = self._validators.get(key)
            if cached is not None:
                return cached

            try:
                from jsonschema import Draft202012Validator  # type: ignore
            except ImportError as exc:  # pragma: no cover — install gate
                raise RuntimeError(
                    "jsonschema package is required for strict event validation; "
                    "add jsonschema>=4.21,<5 to backend/requirements.txt"
                ) from exc

            path = self.schema_dir / f"{event_type}.v{event_version}.schema.json"
            if not path.is_file():
                raise MissingEventSchema(event_type, event_version, path)

            with path.open("r", encoding="utf-8") as fh:
                schema = json.load(fh)

            validator = Draft202012Validator(schema)
            self._validators[key] = validator
            return validator

    def reset(self) -> None:
        with self._lock:
            self._validators.clear()
            self.schema_dir = _DEFAULT_SCHEMA_DIR


_REGISTRY = _SchemaRegistry()


def get_registry() -> _SchemaRegistry:
    """Return the process-wide registry (singleton)."""
    return _REGISTRY


def reset_registry_for_tests() -> None:
    """Test helper — clears the cached validators."""
    _REGISTRY.reset()


def validate_event(envelope: Any) -> list[str]:
    """Run JSON-Schema validation against ``envelope``'s wire shape.

    Returns the list of validation error messages. Empty list ⇒ valid.

    Raises:
        MissingEventSchema: if no schema is registered for the event type/version.
    """
    event_type = getattr(envelope, "event_type", None)
    event_version = getattr(envelope, "event_version", None)
    if not isinstance(event_type, str) or not isinstance(event_version, int):
        # Not our shape; let the envelope's own validation surface the issue.
        return []

    validator = _REGISTRY.get_validator(event_type, event_version)

    payload = getattr(envelope, "payload", None)
    instance = {
        "event_type": event_type,
        "event_version": event_version,
        "payload": dict(payload) if payload is not None else {},
    }

    errors: Iterable[Any] = validator.iter_errors(instance)
    messages: list[str] = []
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path) or "<root>"
        messages.append(f"{loc}: {err.message}")
    return messages
