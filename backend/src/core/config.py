"""
Configuration management using Pydantic Settings.

Supports environment-based configuration with support for both
NVIDIA hosted NIM and self-hosted NIM deployments.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables
    with the same name (case-insensitive).
    """
    
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),  # Check both project root and backend directory
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ==========================================
    # Application Settings
    # ==========================================
    app_name: str = Field(default="rag-backend", description="Application name")
    app_env: str = Field(default="development", description="Environment (development/staging/production)")
    debug: bool = Field(default=True, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # ==========================================
    # API Server Configuration
    # ==========================================
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=4, description="Number of Gunicorn workers")
    
    # ==========================================
    # NVIDIA NIM Configuration
    # ==========================================
    nvidia_api_key: str = Field(..., description="NVIDIA API key")
    nvidia_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        description="NVIDIA NIM base URL (change for self-hosted)"
    )
    
    # Core Models (Enterprise)
    nvidia_llm_model: str = Field(
        default="nvidia/llama-3.3-nemotron-super-49b-v1",
        description="NVIDIA LLM model name (enterprise: llama-3.3-nemotron-super-49b)"
    )
    nvidia_embed_model: str = Field(
        default="nvidia/llama-3.2-nv-embedqa-1b-v2",
        description="NVIDIA embedding model name"
    )
    nvidia_rerank_model: str = Field(
        default="nvidia/llama-3.2-nv-rerankqa-1b-v2",
        description="NVIDIA reranker model name"
    )
    
    # Multimodal Parsing Models
    nvidia_page_elements_model: str = Field(
        default="nvidia/nemoretriever-page-elements-v2",
        description="NVIDIA page elements extraction model"
    )
    nvidia_table_model: str = Field(
        default="nvidia/nemoretriever-table-structure-v1",
        description="NVIDIA table structure extraction model"
    )
    nvidia_graphic_model: str = Field(
        default="nvidia/nemoretriever-graphic-elements-v1",
        description="NVIDIA graphic/chart extraction model"
    )
    nvidia_ocr_model: str = Field(
        default="paddleocr",
        description="OCR model for scanned documents"
    )
    
    nvidia_timeout: int = Field(default=60, description="NVIDIA API timeout in seconds")
    nvidia_max_retries: int = Field(default=3, description="Maximum retry attempts for NVIDIA API")
    
    # ==========================================
    # PostgreSQL Database
    # ==========================================
    postgres_host: str = Field(default="postgres", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="ragdb", description="PostgreSQL database name")
    postgres_user: str = Field(default="raguser", description="PostgreSQL username")
    postgres_password: str = Field(default="ragpass123", description="PostgreSQL password")
    
    @computed_field
    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @computed_field
    @property
    def database_url_sync(self) -> str:
        """Construct sync PostgreSQL connection URL (for Alembic)."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    # ==========================================
    # Qdrant Vector Database
    # ==========================================
    qdrant_host: str = Field(default="qdrant", description="Qdrant host")
    qdrant_port: int = Field(default=6333, description="Qdrant port")
    qdrant_collection: str = Field(default="documents", description="Qdrant collection name")
    qdrant_vector_size: int = Field(default=1024, description="Vector embedding dimension")
    
    @computed_field
    @property
    def qdrant_url(self) -> str:
        """Construct Qdrant connection URL."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"
    
    # ==========================================
    # Redis Cache
    # ==========================================
    redis_host: str = Field(default="redis", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    redis_queue_name: str = Field(default="ingestion_queue", description="Redis queue name for ingestion jobs")
    
    @computed_field
    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL."""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    # ==========================================
    # Security & Authentication
    # ==========================================
    jwt_secret_key: str = Field(
        default="your-super-secret-jwt-key-change-in-production",
        description="JWT secret key"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=60,
        description="Access token expiration in minutes"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token expiration in days"
    )
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=100, description="Max requests per window")
    rate_limit_window_seconds: int = Field(default=60, description="Rate limit window in seconds")
    
    # ==========================================
    # RAG Configuration
    # ==========================================
    chunk_size: int = Field(default=768, description="Document chunk size in tokens (larger for tables/financial data)")
    chunk_overlap: int = Field(default=100, description="Overlap between chunks (increased for context continuity)")
    top_k_retrieval: int = Field(default=12, description="Number of chunks to retrieve (increased for comprehensive coverage)")
    rerank_top_k: int = Field(default=6, description="Number of chunks after reranking")
    max_context_tokens: int = Field(default=6144, description="Maximum context tokens (increased for more context)")
    
    # Hybrid Search Configuration
    hybrid_search_enabled: bool = Field(default=True, description="Enable hybrid semantic + keyword search")
    keyword_search_weight: float = Field(default=0.3, description="Weight for keyword search (0-1, rest goes to semantic)")
    enable_reranking: bool = Field(default=True, description="Enable reranking of results")
    
    # ==========================================
    # Ingestion Settings
    # ==========================================
    max_file_size_mb: int = Field(default=50, description="Maximum file size in MB")
    allowed_extensions: str = Field(
        default="pdf,docx,txt",
        description="Comma-separated allowed file extensions"
    )
    ingestion_batch_size: int = Field(default=10, description="Batch size for ingestion")
    
    @computed_field
    @property
    def allowed_extensions_list(self) -> list[str]:
        """Parse allowed extensions into a list."""
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",")]
    
    # ==========================================
    # Observability
    # ==========================================
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")
    metrics_port: int = Field(default=9090, description="Metrics port")
    tracing_enabled: bool = Field(default=True, description="Enable distributed tracing")
    otlp_endpoint: str = Field(default="http://jaeger:4317", description="OpenTelemetry collector endpoint")
    ragas_evaluation_enabled: bool = Field(default=False, description="Enable RAGAS evaluation")
    
    # ==========================================
    # MinIO Object Storage
    # ==========================================
    minio_endpoint: str = Field(default="minio:9000", description="MinIO endpoint")
    minio_access_key: str = Field(default="ragadmin", description="MinIO access key")
    minio_secret_key: str = Field(default="ragpass123", description="MinIO secret key")
    minio_secure: bool = Field(default=False, description="Use HTTPS for MinIO")
    minio_bucket_documents: str = Field(default="documents", description="MinIO bucket for documents")
    minio_bucket_assets: str = Field(default="parsed-assets", description="MinIO bucket for parsed assets")
    
    # ==========================================
    # Neo4j Graph Database
    # ==========================================
    neo4j_uri: str = Field(default="bolt://neo4j:7687", description="Neo4j Bolt URI")
    neo4j_username: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="password123", description="Neo4j password")

    # ==========================================
    # Guardrails Configuration
    # ==========================================
    guardrails_enabled: bool = Field(default=False, description="Enable content guardrails")
    input_guardrails: bool = Field(default=True, description="Enable input validation guardrails")
    output_guardrails: bool = Field(default=True, description="Enable output validation guardrails")
    
    # ==========================================
    # Helper Properties
    # ==========================================
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.app_env.lower() == "development"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure settings are loaded only once
    and reused across the application.
    """
    return Settings()


# Global settings instance for convenient imports
settings = get_settings()
