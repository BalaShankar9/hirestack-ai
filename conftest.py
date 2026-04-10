"""Root conftest: configure sys.path so ai_engine and backend app are both importable."""
import sys
import os

# Allow `import ai_engine` from the repo root
_root = os.path.dirname(__file__)
if _root not in sys.path:
    sys.path.insert(0, _root)

# Allow `from app.core.config import settings` (used by ai_engine/client.py)
_backend = os.path.join(_root, "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)
