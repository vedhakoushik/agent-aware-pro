"""
Central configuration — all settings come from environment / .env, validated once.

Nothing in the app reads os.getenv directly; everything goes through `settings`, so
there is one place to see exactly what the system needs and what's optional.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── LLM providers (the reasoning layer — NOT data fetching) ──
    groq_api_key: str = ""
    gemini_api_key: str = ""
    gemini_api_keys: str = ""   # comma-separated pool — rotates so one free-tier key
                                # exhausting its quota mid-run doesn't stall reasoning
    ollama_enabled: bool = False
    ollama_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://localhost:11434/v1"

    # ── Real data providers (structured APIs — the professional data layer) ──
    # When these are blank the app runs on realistic DEMO data so it works end-to-end
    # out of the box; fill them in to switch a connector to live data.
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    serpapi_key: str = ""
    rapidapi_key: str = ""
    rapidapi_host: str = ""

    # ── Infra ──
    redis_url: str = ""              # blank → in-process cache
    cache_ttl_seconds: int = 300
    source_timeout_seconds: float = 8.0

    # ── Slack (read-only channel viewer) ──
    slack_bot_token: str = ""

    # ── Observability ──
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    @property
    def llm_configured(self) -> bool:
        return bool(self.groq_api_key or self.gemini_api_key or self.ollama_enabled)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
