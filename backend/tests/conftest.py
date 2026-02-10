"""
Pytest configuration and fixtures.
"""

import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_nvidia_response() -> dict:
    """Mock NVIDIA API response."""
    return {
        "choices": [
            {
                "message": {
                    "content": "This is a mock response from NVIDIA NIM."
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }


@pytest.fixture
def mock_embedding_response() -> dict:
    """Mock NVIDIA embedding response."""
    return {
        "data": [
            {"embedding": [0.1] * 1024, "index": 0}
        ],
        "usage": {"total_tokens": 10},
    }


@pytest.fixture
def mock_rerank_response() -> dict:
    """Mock NVIDIA reranker response."""
    return {
        "rankings": [
            {"index": 0, "logit": 0.95},
            {"index": 2, "logit": 0.85},
            {"index": 1, "logit": 0.75},
        ]
    }


@pytest.fixture
def mock_httpx_client(mock_nvidia_response: dict) -> AsyncMock:
    """Mock httpx async client."""
    mock_response = MagicMock()
    mock_response.json.return_value = mock_nvidia_response
    mock_response.raise_for_status = MagicMock()
    
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    
    return mock_client


@pytest.fixture
def sample_document_text() -> str:
    """Sample document text for testing."""
    return """
    Introduction to Machine Learning

    Machine learning is a subset of artificial intelligence (AI) that enables 
    systems to learn and improve from experience without being explicitly programmed.
    
    Types of Machine Learning
    
    1. Supervised Learning: The algorithm learns from labeled training data.
    2. Unsupervised Learning: The algorithm finds patterns in unlabeled data.
    3. Reinforcement Learning: The agent learns through trial and error.
    
    Applications
    
    Machine learning has numerous applications including:
    - Natural Language Processing
    - Computer Vision
    - Recommendation Systems
    - Fraud Detection
    """


@pytest.fixture
def sample_chunks() -> list:
    """Sample document chunks for testing."""
    return [
        {
            "content": "Machine learning is a subset of AI.",
            "document_id": "doc_123",
            "source": "test.pdf",
            "chunk_index": 0,
        },
        {
            "content": "Supervised learning uses labeled data.",
            "document_id": "doc_123",
            "source": "test.pdf",
            "chunk_index": 1,
        },
    ]
