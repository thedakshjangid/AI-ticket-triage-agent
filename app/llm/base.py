"""Provider-neutral types for tool-calling LLMs.

The agent only talks to these types, so switching between OpenAI, Anthropic or the offline
mock is a config change. Each provider converts to and from its own API format.

Conversation messages use one of three shapes:
    {"role": "user", "content": str}
    {"role": "assistant", "text": str | None, "tool_calls": [ToolCall, ...]}
    {"role": "tool", "tool_call_id": str, "name": str, "content": str}
"""

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    # Set when the model sent arguments that weren't valid JSON, so the agent can report it back.
    parse_error: str | None = None


@dataclass
class LLMTurn:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, messages: list[dict], tools: list[ToolSpec]) -> LLMTurn: ...
