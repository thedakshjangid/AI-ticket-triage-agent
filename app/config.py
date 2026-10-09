"""Settings read from environment variables (see .env.example)."""

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    webhook_secret: str
    api_key: str
    llm_provider: str  # "openai", "anthropic" or "mock"
    openai_model: str
    anthropic_model: str
    max_agent_steps: int
    max_body_chars: int
    signature_tolerance_seconds: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./triage.db"),
        webhook_secret=os.getenv("WEBHOOK_SECRET", "dev-webhook-secret"),
        api_key=os.getenv("API_KEY", "dev-api-key"),
        llm_provider=os.getenv("LLM_PROVIDER", "mock").lower(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5"),
        max_agent_steps=int(os.getenv("MAX_AGENT_STEPS", "6")),
        max_body_chars=int(os.getenv("MAX_BODY_CHARS", "4000")),
        signature_tolerance_seconds=int(os.getenv("SIGNATURE_TOLERANCE_SECONDS", "300")),
    )
