"""Temporal scaffold (PR m6-pr17).

This package is the foundation for durable generation workflows. It
intentionally does no I/O at import time so the FastAPI process can
import it freely; the worker entrypoint is the only place that opens
a connection to a Temporal cluster.
"""

from .config import TemporalSettings, load_settings

__all__ = ["TemporalSettings", "load_settings"]
