"""Environment-backed application settings."""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache
from uuid import UUID

from pydantic import Field, HttpUrl, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported application environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


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
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/mneme"
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
    demo_token_sha256: SecretStr | None = None
    demo_user_id: UUID | None = None
    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_summary_model: str = "claude-opus-4-8"
    llm_qa_model: str = "claude-opus-4-8"
    ai_daily_budget_usd: Decimal = Field(default=Decimal("5"), gt=Decimal(0))
    ai_cache_enabled: bool = True
    ai_summary_cache_ttl_seconds: int = Field(default=7 * 24 * 3600, ge=1)
    ai_qa_cache_ttl_seconds: int = Field(default=24 * 3600, ge=1)

    @property
    def use_json_logs(self) -> bool:
        """Use machine-readable logs outside local development."""
        return self.environment is not Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""
    return Settings()
