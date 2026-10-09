from app.config import get_settings
from app.llm.base import LLMProvider, LLMTurn, ToolCall, ToolSpec


def get_provider(name: str | None = None) -> LLMProvider:
    settings = get_settings()
    name = (name or settings.llm_provider).lower()
    if name == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(settings.openai_model)
    if name == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings.anthropic_model)
    if name == "mock":
        from app.llm.mock_provider import MockProvider

        return MockProvider()
    raise ValueError(f"Unknown LLM_PROVIDER '{name}' (expected openai, anthropic or mock)")


__all__ = ["LLMProvider", "LLMTurn", "ToolCall", "ToolSpec", "get_provider"]
