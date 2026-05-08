"""backend.app.core — lowest layer.

Settings, auth, observability, queue, events, idempotency. May not
import from ``backend.app.api`` or ``backend.app.services`` (enforced
by `.importlinter` contract C2).
"""
