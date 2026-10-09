from app.llm.base import LLMTurn, ToolCall, ToolSpec


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, client=None, max_tokens: int = 1024):
        if client is None:
            from anthropic import Anthropic

            client = Anthropic()  # reads ANTHROPIC_API_KEY
        self.client = client
        self.model = model
        self.max_tokens = max_tokens

    @staticmethod
    def to_anthropic_messages(messages: list[dict]) -> list[dict]:
        """Claude expects tool results inside a *user* message, grouped together."""
        out: list[dict] = []
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                blocks: list[dict] = []
                if m.get("text"):
                    blocks.append({"type": "text", "text": m["text"]})
                for tc in m.get("tool_calls", []):
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                out.append({"role": "assistant", "content": blocks})
            elif m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                prev = out[-1] if out else None
                if prev and prev["role"] == "user" and isinstance(prev["content"], list):
                    prev["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    def complete(self, system: str, messages: list[dict], tools: list[ToolSpec]) -> LLMTurn:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=system,
            messages=self.to_anthropic_messages(messages),
            tools=[{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools],
            tool_choice={"type": "any"},  # must call a tool; submit_triage ends the loop
        )
        text_parts, calls = [], []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))
        return LLMTurn(text="\n".join(text_parts) or None, tool_calls=calls)
