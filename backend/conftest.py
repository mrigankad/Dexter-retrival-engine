"""
Root pytest configuration.

Sets the environment *before* ``src.core.config`` is imported so the engine
runs fully in-process: SQLite, in-memory Qdrant, no Redis, inline ingestion,
and fake model services (see tests/fakes.py).
"""

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent.absolute()
for p in (str(BACKEND_ROOT), str(BACKEND_ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

_TEST_ENV = {
    "APP_ENV": "test",
    "DEBUG": "true",
    "LOG_LEVEL": "WARNING",
    "USE_SQLITE": "true",
    "SQLITE_PATH": str(BACKEND_ROOT / ".pytest_data" / "test.db"),
    "QDRANT_MODE": "memory",
    "QDRANT_VECTOR_SIZE": "64",
    "REDIS_ENABLED": "false",
    "INGESTION_MODE": "inline",
    "UPLOAD_DIR": str(BACKEND_ROOT / ".pytest_data" / "uploads"),
    "NVIDIA_API_KEY": "",
    "KNOWLEDGE_BACKEND": "local",
    "TRACING_ENABLED": "false",
    "CHUNK_SIZE": "120",
    "CHUNK_OVERLAP": "20",
    "RERANK_TOP_K": "4",
    "TOP_K_RETRIEVAL": "12",
}
for key, value in _TEST_ENV.items():
    os.environ[key] = value
