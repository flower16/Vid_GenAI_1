"""Application configuration (12-factor, env-driven)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FDIC Part 370 Insurance Determination Platform"
    environment: str = "local"
    log_level: str = "INFO"

    # AI / LLM
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_model: str = "claude-opus-4-8"  # latest, most capable Claude
    llm_temperature: float = 0.0

    # LangSmith observability
    langsmith_api_key: Optional[str] = None
    langsmith_project: str = "fdic-part370"
    langsmith_tracing: bool = False

    # Fireworks AI (LLM-as-judge evals + optional fine-tuning path)
    fireworks_api_key: Optional[str] = None
    # OpenAI-compatible chat endpoint; served OSS model keeps the judge cheap.
    fireworks_base_url: str = "https://api.fireworks.ai/inference/v1"
    fireworks_judge_model: str = "accounts/fireworks/models/llama-v3p1-8b-instruct"
    # Run the Fireworks judges inside every determination (so their scores persist
    # to Snowflake and sync to LangSmith alongside the deterministic evals). Safe
    # by default: with no fireworks_api_key the judges use the free heuristic.
    # Turn off if you set a real key and don't want per-determination model calls.
    fireworks_evals_in_workflow: bool = True

    # Pinecone
    pinecone_api_key: Optional[str] = None
    pinecone_index: str = "fdic-part370"

    # Snowflake
    snowflake_account: Optional[str] = None
    snowflake_user: Optional[str] = None
    snowflake_password: Optional[str] = None
    snowflake_database: str = "FDIC_PART370"
    snowflake_schema: str = "CORE"
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_role: Optional[str] = None

    # Azure AD SSO
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None
    azure_audience: Optional[str] = None


def _export_to_env(s: Settings) -> None:
    """Mirror keys into os.environ for third-party libs that read them directly.

    langchain-pinecone 0.2.0 ignores the pinecone_api_key kwarg in its
    from_texts path and reads PINECONE_API_KEY from the environment; the OpenAI
    and LangSmith clients behave the same way. Pydantic loads .env into this
    settings object but not into os.environ, so bridge them here. Never override
    a value already set in the real environment.
    """
    for env_name, value in (
        ("OPENAI_API_KEY", s.openai_api_key),
        ("PINECONE_API_KEY", s.pinecone_api_key),
        ("LANGSMITH_API_KEY", s.langsmith_api_key),
        ("LANGCHAIN_API_KEY", s.langsmith_api_key),
        ("LANGCHAIN_PROJECT", s.langsmith_project),
        ("LANGCHAIN_TRACING_V2", "true" if s.langsmith_tracing else None),
        ("FIREWORKS_API_KEY", s.fireworks_api_key),
    ):
        if value and not os.environ.get(env_name):
            os.environ[env_name] = value


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _export_to_env(s)
    return s


settings = get_settings()
