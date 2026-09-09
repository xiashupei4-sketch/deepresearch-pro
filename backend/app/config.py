"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_YAML_PATH = BASE_DIR.parent / "config.yaml"

_DEFAULT_SQLITE_URL = f"sqlite+aiosqlite:///{(DATA_DIR / 'deepresearch.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "DeepResearch Pro"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:4173"

    # LLM — empty key => MockLLMProvider (full workflow runnable without API key)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2

    # Database
    database_url: str = _DEFAULT_SQLITE_URL

    # Cache / vector
    redis_url: str = ""
    qdrant_url: str = ""

    # Web search
    web_search_provider: str = "duckduckgo"
    serpapi_key: str = ""

    # Research tuning
    max_reflection_iterations: int = 2
    max_concurrency: int = 3
    agent_timeout: int = 120
    max_tool_calls: int = 10

    # Retrieval tuning
    chunk_size: int = 700
    chunk_overlap: int = 120
    vector_top_k: int = 20
    bm25_top_k: int = 20
    rerank_top_k: int = 8

    # Context engineering
    context_max_tokens: int = 16000
    reserve_output_tokens: int = 3000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
