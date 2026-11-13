"""Configuração central lida de variáveis de ambiente."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_env: str = "production"
    app_name: str = "Monitor Automotivo"
    log_level: str = "INFO"

    # Segurança
    secret_key: str = Field(min_length=32)
    access_token_minutes: int = 480
    cors_origins: str = ""
    login_max_attempts: int = 8
    login_window_seconds: int = 300

    # Infra
    mongo_uri: str
    mongo_db: str = "monitor_automotivo"
    redis_url: str

    display_timezone: str = "America/Sao_Paulo"

    # Coleta de estoque
    scraper_timeout_seconds: int = 30
    scraper_max_pages: int = 30
    scraper_max_redirects: int = 5
    scraper_max_bytes: int = 15_000_000
    inventory_min_ratio: float = 0.5
    playwright_enabled: bool = True

    # Instagram
    instagram_provider: str = "instaloader"
    instagram_session_file: str | None = None
    instagram_session_username: str | None = None
    instagram_posts_limit: int = 24
    instagram_rate_limit: str = "2/m"
    instagram_block_minutes: int = 60
    instagram_followers_tolerance_days: int = 3
    instagram_min_frequency_hours: int = 6

    # Tarefas
    task_max_retries: int = 3
    task_retry_backoff_seconds: int = 60
    run_lease_minutes: int = 45
    scheduler_tick_seconds: int = 60

    @field_validator("instagram_session_file", "instagram_session_username", mode="before")
    @classmethod
    def _empty_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
