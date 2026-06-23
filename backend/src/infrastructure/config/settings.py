"""Application settings — loaded from environment variables only.

Rule 10: All configuration via env/yaml/secret manager. Never hardcoded.
Rule 9: No shared mutable state — Settings is injected via dependency injection.
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure .env is loaded into os.environ for CLI tools and workers
load_dotenv()


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    database_url: PostgresDsn = Field(
        ...,
        alias="DATABASE_URL",
        description="asyncpg-compatible PostgreSQL DSN e.g. postgresql+asyncpg://...",
    )
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    redis_url: RedisDsn = Field(..., alias="REDIS_URL")


class RabbitMQSettings(BaseSettings):
    """RabbitMQ connection settings."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    rabbitmq_url: str = Field(..., alias="RABBITMQ_URL")
    rabbitmq_prefetch_count: int = Field(default=1, alias="RABBITMQ_PREFETCH_COUNT")


class StorageSettings(BaseSettings):
    """MinIO / S3-compatible object storage settings."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    storage_provider: str = Field(default="minio", alias="STORAGE_PROVIDER")
    minio_endpoint: str = Field(..., alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(..., alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(..., alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="audio-files", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")


class OpenAISettings(BaseSettings):
    """OpenAI provider settings — all models configurable independently."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    
    # Custom orchestration API support
    ai_provider_orchestration_api_key: str | None = Field(
        default=None, alias="AI_PROVIDER_ORCHESTRATION_API_KEY"
    )
    ai_provider_orchestration_api_url: str | None = Field(
        default=None, alias="AI_PROVIDER_ORCHESTRATION_API_URL"
    )

    @property
    def active_api_key(self) -> str:
        key = self.ai_provider_orchestration_api_key or self.openai_api_key
        if not key:
            raise ValueError("Must provide either OPENAI_API_KEY or AI_PROVIDER_ORCHESTRATION_API_KEY")
        return key

    # STT provider config
    openai_stt_model: str = Field(default="whisper-1", alias="OPENAI_STT_MODEL")
    openai_stt_temperature: float = Field(default=0.0, alias="OPENAI_STT_TEMPERATURE")
    openai_stt_timeout_seconds: int = Field(default=300, alias="OPENAI_STT_TIMEOUT_SECONDS")

    # Repair provider config (diarization + correction)
    openai_repair_model: str = Field(default="gpt-4o", alias="OPENAI_REPAIR_MODEL")
    openai_repair_temperature: float = Field(default=0.0, alias="OPENAI_REPAIR_TEMPERATURE")
    openai_repair_timeout_seconds: int = Field(default=120, alias="OPENAI_REPAIR_TIMEOUT_SECONDS")

    # Analysis provider config
    openai_analysis_model: str = Field(default="gpt-4o", alias="OPENAI_ANALYSIS_MODEL")
    openai_analysis_temperature: float = Field(default=0.0, alias="OPENAI_ANALYSIS_TEMPERATURE")
    openai_analysis_timeout_seconds: int = Field(
        default=120, alias="OPENAI_ANALYSIS_TIMEOUT_SECONDS"
    )


class AuthSettings(BaseSettings):
    """JWT authentication settings."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=60, alias="JWT_EXPIRE_MINUTES")


class WatcherSettings(BaseSettings):
    """Filesystem watcher settings."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    watcher_audio_dir: str = Field(default="/audio_files", alias="WATCHER_AUDIO_DIR")
    watcher_poll_interval_seconds: int = Field(
        default=5, alias="WATCHER_POLL_INTERVAL_SECONDS"
    )


class AppSettings(BaseSettings):
    """Top-level application settings — composes all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    ws_port: int = Field(default=8001, alias="WS_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    cors_origins: list[str] = Field(
        default=["*"], alias="APP_CORS_ORIGINS"
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_db_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_redis_settings() -> RedisSettings:
    return RedisSettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_rabbitmq_settings() -> RabbitMQSettings:
    return RabbitMQSettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_storage_settings() -> StorageSettings:
    return StorageSettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_openai_settings() -> OpenAISettings:
    return OpenAISettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return AuthSettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_watcher_settings() -> WatcherSettings:
    return WatcherSettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()  # type: ignore[call-arg]
