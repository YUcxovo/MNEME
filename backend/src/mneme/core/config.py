"""Environment-backed application settings."""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, HttpUrl, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported application environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class EmbeddingBackend(StrEnum):
    """Supported embedding backends."""

    OPENAI = "openai"
    FASTEMBED = "fastembed"


class Settings(BaseSettings):
    """Validated settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MNEME_",
        extra="ignore",
        frozen=True,
    )

    app_name: str = "Mneme API"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: str = "INFO"
    api_host: Literal["127.0.0.1"] = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    api_workers: int = Field(default=2, ge=1, le=8)
    api_timeout_seconds: int = Field(default=120, ge=1, le=600)
    api_graceful_timeout_seconds: int = Field(default=90, ge=1, le=300)
    api_keepalive_seconds: int = Field(default=5, ge=1, le=60)
    api_max_requests: int = Field(default=1000, ge=0, le=1_000_000)
    api_max_requests_jitter: int = Field(default=100, ge=0, le=100_000)
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mneme"
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=50)
    database_pool_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    database_pool_recycle_seconds: int = Field(default=1800, ge=1, le=86400)
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    redis_max_connections: int = Field(default=10, ge=1)
    redis_socket_timeout_seconds: float = Field(default=5.0, gt=0)
    arq_queue_name: str = "mneme:jobs"
    arq_max_jobs: int = Field(default=5, ge=1)
    arq_job_timeout_seconds: int = Field(default=300, ge=1)
    arq_max_tries: int = Field(default=3, ge=1)
    arq_health_check_interval_seconds: int = Field(default=30, ge=1)
    arxiv_api_url: HttpUrl = HttpUrl("https://export.arxiv.org/api/query")
    arxiv_user_agent: str = "Mneme/0.1 (+https://github.com/YUcxovo/MNEME)"
    arxiv_request_interval_seconds: float = Field(default=3.0, ge=3.0)
    arxiv_timeout_seconds: float = Field(default=30.0, gt=0)
    arxiv_max_attempts: int = Field(default=3, ge=1, le=10)
    arxiv_max_results: int = Field(default=100, ge=1, le=2000)
    arxiv_daily_categories: str = "cs.AI,cs.LG"
    arxiv_daily_max_results: int = Field(default=20, ge=1, le=2000)
    semantic_scholar_api_url: HttpUrl = HttpUrl("https://api.semanticscholar.org/graph/v1")
    semantic_scholar_api_key: SecretStr | None = None
    semantic_scholar_request_interval_seconds: float = Field(default=1.0, ge=0)
    semantic_scholar_timeout_seconds: float = Field(default=30.0, gt=0)
    semantic_scholar_max_attempts: int = Field(default=3, ge=1, le=10)
    semantic_scholar_batch_size: int = Field(default=100, ge=1, le=500)
    semantic_scholar_page_size: int = Field(default=100, ge=1, le=1000)
    semantic_scholar_max_neighbors: int = Field(default=1000, ge=1, le=9999)
    paper_storage_dir: Path = Path(".data/papers")
    pdf_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    pdf_download_timeout_seconds: float = Field(default=60.0, gt=0)
    pdf_download_max_attempts: int = Field(default=3, ge=1, le=10)
    pdf_min_text_chars: int = Field(default=500, ge=1)
    demo_token_sha256: SecretStr | None = None
    demo_user_id: UUID | None = None
    anthropic_api_key: SecretStr | None = None
    deepseek_api_key: SecretStr | None = None
    deepseek_thinking_enabled: bool = False
    openai_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_summary_model: str = "claude-opus-4-8"
    llm_qa_model: str = "claude-opus-4-8"
    ai_daily_budget_usd: Decimal = Field(default=Decimal("5"), gt=Decimal(0))
    ai_cache_enabled: bool = True
    ai_summary_cache_ttl_seconds: int = Field(default=7 * 24 * 3600, ge=1)
    ai_qa_cache_ttl_seconds: int = Field(default=24 * 3600, ge=1)
    ai_summary_max_input_chars: int = Field(default=60_000, ge=1000)
    ai_summary_max_output_tokens: int = Field(default=1024, ge=64)
    ai_embedding_backend: EmbeddingBackend = EmbeddingBackend.OPENAI
    ai_embedding_model: str = "text-embedding-3-small"
    ai_local_embedding_model: str = "BAAI/bge-small-en-v1.5"
    ai_embedding_batch_size: int = Field(default=64, ge=1, le=2048)
    ai_chunk_max_tokens: int = Field(default=450, ge=50)
    ai_chunk_overlap_tokens: int = Field(default=60, ge=0)
    ai_retrieval_top_k: int = Field(default=8, ge=1, le=50)
    ai_qa_rerank_top_n: int = Field(default=4, ge=1, le=20)
    ai_qa_min_evidence_score: float = Field(default=0.25, ge=0, le=1)
    ai_qa_max_output_tokens: int = Field(default=512, ge=64)
    ai_recommendation_candidate_days: int = Field(default=14, ge=1)
    ai_recommendation_max_entries: int = Field(default=10, ge=1, le=50)

    @property
    def use_json_logs(self) -> bool:
        """Use machine-readable logs outside local development."""
        return self.environment is not Environment.DEVELOPMENT

    @property
    def daily_arxiv_categories(self) -> tuple[str, ...]:
        """Return configured daily categories in stable deduplicated order."""
        categories = (
            item.strip() for item in self.arxiv_daily_categories.split(",") if item.strip()
        )
        return tuple(dict.fromkeys(categories))


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""
    return Settings()
