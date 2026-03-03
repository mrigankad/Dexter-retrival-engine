"""
Pytest configuration and shared fixtures for the test suite.
"""

import sys
import os
from pathlib import Path

# Add backend root to Python path so src/ imports work
backend_root = Path(__file__).parent.absolute()
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

import pytest
from unittest.mock import AsyncMock, MagicMock


# ──────────────────────────────────────────────────────────────────────────────
# Pytest Configuration
# ──────────────────────────────────────────────────────────────────────────────

def pytest_configure(config):
    """Configure pytest with markers and settings."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (for pytest-asyncio)"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (fast, mocked)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (slow, real services)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Global Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def backend_root_dir() -> Path:
    """Get backend root directory."""
    return Path(__file__).parent.absolute()


@pytest.fixture(scope="session")
def src_dir(backend_root_dir) -> Path:
    """Get src directory."""
    return backend_root_dir / "src"


@pytest.fixture(scope="session")
def test_dir(backend_root_dir) -> Path:
    """Get tests directory."""
    return backend_root_dir / "tests"


# ──────────────────────────────────────────────────────────────────────────────
# Mock Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_service():
    """Create a mock NVIDIA LLM service."""
    mock = AsyncMock()
    mock.generate = AsyncMock(return_value='{"response": "test"}')
    return mock


@pytest.fixture
def mock_retrieval_service():
    """Create a mock retrieval service."""
    mock = AsyncMock()
    mock.retrieve = AsyncMock(return_value=[
        {"id": "1", "text": "Document 1", "score": 0.9},
        {"id": "2", "text": "Document 2", "score": 0.8},
    ])
    return mock


@pytest.fixture
def mock_embedding_service():
    """Create a mock embedding service."""
    mock = AsyncMock()
    mock.embed = AsyncMock(return_value=[0.1, 0.2, 0.3] * 340)  # 1024 dimensions
    return mock


# ──────────────────────────────────────────────────────────────────────────────
# Event Loop
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for pytest-asyncio."""
    import asyncio
    try:
        # Windows requires ProactorEventLoop for subprocesses
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except AttributeError:
        # Non-Windows systems
        pass
