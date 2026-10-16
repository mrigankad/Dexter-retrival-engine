import asyncio
import os
import shutil
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from fakes import FakeEmbeddingService, FakeLLM, FakeReranker

SAMPLES = Path(__file__).parent / "samples"
DATA_DIR = Path(__file__).parent.parent / ".pytest_data"


@pytest.fixture(scope="session", autouse=True)
def _clean_data_dir():
    shutil.rmtree(DATA_DIR, ignore_errors=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "uploads").mkdir(exist_ok=True)
    yield
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture
def fake_llm():
    return FakeLLM(responses={
        "Evidence:": "Hotel stays in Tier 1 cities are capped at **220 USD** per night [1]. Meals are limited to 75 USD per day [2]. Unsupported claim [9].",
        "chatting with you": "Hi! I answer questions about your documents.",
        "decompose questions": '{"sub_questions": ["What is the hotel limit in Tier 1 cities?", "What is the hotel limit elsewhere?"], "alternate_phrasings": ["hotel nightly cap by city tier"], "synthesis_strategy": "comparison_table", "needs_clarification": false, "reasoning": "two sides"}',
        "Classify the user's message": '{"intent": "KNOWLEDGE", "confidence": 0.9, "reason": "test"}',
    })


@pytest_asyncio.fixture
async def services(fake_llm):
    """Install fakes + reset all singletons; yields (llm, embedder, reranker)."""
    from src.services.llm.embedding_service import set_embedding_service
    from src.services.llm.nvidia_llm_service import set_llm_service
    from src.services.llm.reranker_service import set_reranker_service
    from src.infrastructure.vector_store.qdrant_store import reset_qdrant_for_tests
    from src.retrieval.hybrid_retriever import reset_hybrid_retriever
    from src.ingestion.pipeline import reset_ingestion_pipeline
    from src.knowledge import reset_registry
    from src.orchestrator.engine import set_engine
    from src.api.v1.chat_routes import reset_engine_cache
    from src.infrastructure.database import init_db, close_db
    from src.infrastructure.database.session_manager import reset_db_for_tests

    emb, rr = FakeEmbeddingService(), FakeReranker()
    set_embedding_service(emb)
    set_reranker_service(rr)
    set_llm_service(fake_llm)
    await reset_qdrant_for_tests()
    reset_hybrid_retriever()
    reset_ingestion_pipeline()
    reset_registry()
    set_engine(None)
    reset_engine_cache()
    await init_db()
    await reset_db_for_tests()
    await init_db()
    yield fake_llm, emb, rr
    await close_db()
    await reset_qdrant_for_tests()
    reset_hybrid_retriever()
    reset_ingestion_pipeline()
    reset_registry()
    set_engine(None)
    set_embedding_service(None)
    set_reranker_service(None)
    set_llm_service(None)


@pytest_asyncio.fixture
async def indexed_policy(services):
    """Ingest the sample policy document; returns its document_id."""
    from src.contracts import IngestionJob
    from src.infrastructure.database import Document, session_scope
    from src.ingestion import get_ingestion_pipeline

    did = str(uuid.uuid4())
    async with session_scope() as s:
        s.add(Document(id=uuid.UUID(did), filename="policy.md", file_type="md", file_size=10, status="pending"))
    result = await get_ingestion_pipeline().process(IngestionJob(document_id=did, file_path=str(SAMPLES / "policy.md"), filename="policy.md"))
    assert result.status == "completed", result.error
    return did


@pytest_asyncio.fixture
async def client(services):
    import httpx
    from main import app

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    r = await client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
