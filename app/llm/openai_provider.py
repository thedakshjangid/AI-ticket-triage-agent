import json

from app.llm.base import LLMTurn, ToolCall, ToolSpec


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, client=None):
        if client is None:
            from openai import OpenAI

            client = OpenAI()  # reads OPENAI_API_KEY
        self.client = client
        self.model = model

    @staticmethod
    def to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                msg: dict = {"role": "assistant", "content": m.get("text")}
                if m.get("tool_calls"):
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in m["tool_calls"]
                    ]
                out.append(msg)
            elif m["role"] == "tool":
                out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
        return out

    def complete(self, system: str, messages: list[dict], tools: list[ToolSpec]) -> LLMTurn:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=self.to_openai_messages(system, messages),
            tools=[
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
                }
                for t in tools
            ],
            tool_choice="required",  # every turn must be a tool call; submit_triage ends the loop
        )
        message = response.choices[0].message
        calls = []
        for tc in message.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
                calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
            except json.JSONDecodeError as e:
                calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments={}, parse_error=str(e)))
        return LLMTurn(text=message.content, tool_calls=calls)
