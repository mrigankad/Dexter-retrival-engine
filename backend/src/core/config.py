"""
Configuration management using Pydantic Settings.

Every setting can be overridden through environment variables (case-insensitive).
The defaults are chosen so the engine can boot with *no* external services:
SQLite instead of PostgreSQL, in-memory Qdrant, no Redis, mock LLM-free paths
for tests. Production deployments set the real endpoints.
"""

from functools import lru_cache
from typing import List, Literal, Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ==========================================
    # Application
    # ==========================================
    app_name: str = Field(default="dexter-retrieval-engine")
    app_env: str = Field(default="development", description="development | staging | production | test")
    debug: bool = Field(default=True)
    log_level: str = Field(default="INFO")
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_workers: int = Field(default=4)
    cors_origins: str = Field(default="*", description="Comma separated list of allowed origins")

    # ==========================================
    # Knowledge backend selection
    # ==========================================
    knowledge_backend: Literal["local", "foundry_iq", "mock"] = Field(
        default="local",
        description="Which KnowledgeAdapter answers knowledge.retrieve: local (Qdrant hybrid), foundry_iq (Azure AI Search agentic retrieval), mock",
    )
    knowledge_fallback_backend: Optional[Literal["local", "foundry_iq", "mock"]] = Field(
        default=None, description="Optional backend used when the primary one fails or returns nothing",
    )

    # ==========================================
    # NVIDIA NIM (LLM / embeddings / rerank)
    # ==========================================
    nvidia_api_key: str = Field(default="", description="NVIDIA API key (nvapi-...)")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1")
    nvidia_llm_model: str = Field(default="nvidia/nemotron-3-super-120b-a12b", description="Primary chat model (verify on build.nvidia.com)")
    nvidia_llm_fallback_models: str = Field(
        default="nvidia/llama-3.3-nemotron-super-49b-v1.5,meta/llama-3.1-70b-instruct",
        description="Comma separated models tried in order on 404/410/429 from the primary",
    )
    nvidia_llm_fast_model: str = Field(
        default="nvidia/nemotron-3-nano-30b-a3b",
        description="Cheap model for routing / planning / query rewriting",
    )
    nvidia_embed_model: str = Field(default="nvidia/llama-nemotron-embed-1b-v2", description="2048-d, MRL 384-2048, 8k ctx")
    nvidia_embed_dimensions: Optional[int] = Field(default=None, description="Matryoshka truncation (must equal QDRANT_VECTOR_SIZE)")
    nvidia_rerank_model: str = Field(default="nvidia/llama-nemotron-rerank-1b-v2")
    nvidia_rerank_url: str = Field(
        default="https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-1b-v2/reranking",
        description="Full URL of the NIM reranking endpoint",
    )
    nvidia_page_elements_model: str = Field(default="nvidia/nemoretriever-page-elements-v2")
    nvidia_table_model: str = Field(default="nvidia/nemoretriever-table-structure-v1")
    nvidia_graphic_model: str = Field(default="nvidia/nemoretriever-graphic-elements-v1")
    nvidia_ocr_model: str = Field(default="paddleocr")
    nvidia_timeout: int = Field(default=90)
    nvidia_max_retries: int = Field(default=3)

    # ==========================================
    # Microsoft Foundry IQ / Azure AI Search agentic retrieval
    # ==========================================
    azure_search_endpoint: str = Field(default="", description="https://<service>.search.windows.net")
    azure_search_api_key: str = Field(default="", description="Admin/query key; leave empty to use Entra bearer token")
    azure_search_bearer_token: str = Field(default="", description="Optional Entra ID access token for Azure AI Search")
    azure_search_api_version: str = Field(default="2026-08-01-preview", description="2026-04-01 (GA, minimal/extractive only) or 2026-08-01-preview (low/medium, synthesis, MCP)")
    foundry_iq_knowledge_base: str = Field(default="", description="Knowledge base name in Azure AI Search")
    foundry_iq_knowledge_source: str = Field(default="", description="Optional searchIndex knowledge source name used for filterAddOn scoping")
    foundry_iq_max_runtime_seconds: int = Field(default=30)
    foundry_iq_reasoning_effort: Literal["minimal", "low", "medium"] = Field(default="low")
    foundry_iq_include_activity: bool = Field(default=True)
    foundry_iq_max_results: int = Field(default=10)

    # ==========================================
    # Relational database (PostgreSQL or SQLite)
    # ==========================================
    database_url: Optional[str] = Field(
        default=None,
        description="Full async SQLAlchemy URL. If unset, built from POSTGRES_* or SQLite when USE_SQLITE=true",
    )
    use_sqlite: bool = Field(default=False, description="Use a local SQLite file instead of PostgreSQL")
    sqlite_path: str = Field(default="./data/dexter.db")
    postgres_host: str = Field(default="postgres")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="ragdb")
    postgres_user: str = Field(default="raguser")
    postgres_password: str = Field(default="ragpass123")
    db_echo: bool = Field(default=False)

    @computed_field
    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if self.use_sqlite or self.app_env.lower() == "test":
            return f"sqlite+aiosqlite:///{self.sqlite_path}"
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @computed_field
    @property
    def database_url_sync(self) -> str:
        return self.effective_database_url.replace("+asyncpg", "").replace("+aiosqlite", "")

    # ==========================================
    # Qdrant
    # ==========================================
    qdrant_mode: Literal["server", "memory", "path"] = Field(
        default="server", description="server = remote Qdrant; memory = in-process (tests); path = local on-disk"
    )
    qdrant_host: str = Field(default="qdrant")
    qdrant_port: int = Field(default=6333)
    qdrant_api_key: Optional[str] = Field(default=None)
    qdrant_path: str = Field(default="./data/qdrant")
    qdrant_collection: str = Field(default="documents")
    qdrant_vector_size: int = Field(default=2048, description="Dense embedding dimension of NVIDIA_EMBED_MODEL")
    qdrant_sparse_enabled: bool = Field(default=True, description="Index BM25-style sparse vectors for hybrid search")
    qdrant_on_disk: bool = Field(default=False)

    @computed_field
    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    # ==========================================
    # Redis (optional: queue, cache, rate limiting)
    # ==========================================
    redis_enabled: bool = Field(default=True)
    redis_host: str = Field(default="redis")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: Optional[str] = Field(default=None)
    redis_queue_name: str = Field(default="ingestion_queue")

    @computed_field
    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ==========================================
    # Security
    # ==========================================
    jwt_secret_key: str = Field(default="your-super-secret-jwt-key-change-in-production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_token_expire_minutes: int = Field(default=60)
    jwt_refresh_token_expire_days: int = Field(default=7)
    rate_limit_requests: int = Field(default=100)
    rate_limit_window_seconds: int = Field(default=60)
    allow_anonymous_chat: bool = Field(default=True, description="Allow /chat without a JWT (dev only)")
    default_admin_username: str = Field(default="admin")
    default_admin_password: str = Field(default="admin123")

    # ==========================================
    # Retrieval
    # ==========================================
    chunk_size: int = Field(default=512, description="Target chunk size in tokens")
    chunk_overlap: int = Field(default=64)
    chunk_min_tokens: int = Field(default=40, description="Chunks smaller than this are merged with neighbours")
    contextual_headers: bool = Field(default=True, description="Prefix chunks with doc title + section path before embedding")
    top_k_retrieval: int = Field(default=24, description="Candidates fetched from each index before fusion")
    rerank_top_k: int = Field(default=8, description="Chunks kept after reranking")
    max_context_tokens: int = Field(default=6144)
    hybrid_search_enabled: bool = Field(default=True)
    rrf_k: int = Field(default=60)
    enable_reranking: bool = Field(default=True)
    reranker_backend: Literal["nvidia", "local", "none"] = Field(
        default="nvidia", description="nvidia = NIM /reranking API; local = sentence-transformers CrossEncoder; none = fusion order"
    )
    local_reranker_model: str = Field(default="BAAI/bge-reranker-v2-m3")
    multi_query_enabled: bool = Field(default=True, description="Generate alternate phrasings for complex queries")
    max_sub_queries: int = Field(default=4)
    max_tool_calls: int = Field(default=4)
    min_relevance_score: float = Field(default=0.0, description="Drop chunks with fused score below this")
    embedding_batch_size: int = Field(default=16)
    embedding_cache_size: int = Field(default=2048)

    # ==========================================
    # Ingestion
    # ==========================================
    upload_dir: str = Field(default="./uploads")
    max_file_size_mb: int = Field(default=50)
    allowed_extensions: str = Field(default="pdf,docx,txt,md,html,csv")
    ingestion_batch_size: int = Field(default=10)
    ingestion_mode: Literal["queue", "inline"] = Field(
        default="queue", description="queue = Redis worker; inline = process in the API process (dev/tests)"
    )
    parser_backend: Literal["auto", "docling", "pymupdf", "pypdf"] = Field(default="auto")
    enable_knowledge_graph: bool = Field(default=False, description="Extract triplets into Neo4j during ingestion")
    enable_object_storage: bool = Field(default=False, description="Archive originals to MinIO")

    @computed_field
    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",") if ext.strip()]

    # ==========================================
    # Observability / evaluation
    # ==========================================
    enable_metrics: bool = Field(default=True)
    metrics_port: int = Field(default=9090)
    tracing_enabled: bool = Field(default=False)
    otlp_endpoint: str = Field(default="http://jaeger:4317")
    ragas_evaluation_enabled: bool = Field(default=False)
    persist_traces: bool = Field(default=True, description="Store per-query traces in the database")

    # ==========================================
    # MinIO (optional)
    # ==========================================
    minio_endpoint: str = Field(default="minio:9000")
    minio_access_key: str = Field(default="ragadmin")
    minio_secret_key: str = Field(default="ragpass123")
    minio_secure: bool = Field(default=False)
    minio_bucket_documents: str = Field(default="documents")
    minio_bucket_assets: str = Field(default="parsed-assets")

    # ==========================================
    # Neo4j (optional)
    # ==========================================
    neo4j_uri: str = Field(default="bolt://neo4j:7687")
    neo4j_username: str = Field(default="neo4j")
    neo4j_password: str = Field(default="password123")

    # ==========================================
    # Guardrails
    # ==========================================
    guardrails_enabled: bool = Field(default=True)
    input_guardrails: bool = Field(default=True)
    output_guardrails: bool = Field(default=True)

    # ==========================================
    # Helpers
    # ==========================================
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def nvidia_llm_fallback_list(self) -> List[str]:
        return [m.strip() for m in self.nvidia_llm_fallback_models.split(",") if m.strip()]

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() == "test"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_nvidia_key(self) -> bool:
        return bool(self.nvidia_api_key) and not self.nvidia_api_key.startswith("your-")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
