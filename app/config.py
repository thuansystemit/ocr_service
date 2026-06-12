"""Application configuration via pydantic-settings.

All settings are read from environment variables prefixed with ``OCR_`` (plus a
few provider-native vars like ``ANTHROPIC_API_KEY`` that must keep their
canonical names). Instantiate once via :func:`get_settings`.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OCR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    env: Environment = Environment.LOCAL
    log_level: str = "INFO"
    log_json: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://ocr_app:changeme_in_production@localhost:5432/ocr",
        description="Async DSN for app/worker (RLS-enforced ocr_app role).",
    )
    migration_database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ocr",
        description="Sync DSN for Alembic (privileged role).",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Worker pool ---
    worker_default_concurrency: int = Field(default=10, ge=1, le=1000)

    # --- Ingest / storage ---
    max_file_size_bytes: int = Field(default=20 * 1024 * 1024, ge=1)  # 20 MB default
    allowed_mime_types: tuple[str, ...] = (
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    storage_backend: str = "local"  # local | s3 (s3 in a later sprint)
    storage_local_path: str = "./data/documents"

    # --- Parsing ---
    parser_backend: str = "local"  # local | llamaparse
    llama_cloud_api_key: SecretStr | None = None

    # --- Auth ---
    jwt_public_key_path: str = "./deploy/keys/jwt_public.pem"
    jwt_issuer: str = "ocr-platform"
    jwt_audience: str = "ocr-api"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = "ocr_few_shot"
    embedding_dim: int = 1536

    # --- LLM ---
    llm_primary_model: str = "claude-sonnet-4-6"
    llm_fallback_model: str = "gpt-4o"

    # --- PII encryption ---
    pii_encryption_key: SecretStr | None = None

    @property
    def is_production(self) -> bool:
        return self.env == Environment.PROD

    @property
    def checkpoint_dsn(self) -> str:
        """libpq-style DSN for langgraph-checkpoint-postgres (psycopg), derived
        from the async SQLAlchemy URL (which uses the asyncpg driver)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one per process)."""
    return Settings()
