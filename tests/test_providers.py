"""Check the OpenAI and Anthropic adapters build correct requests, using fake clients (no API calls)."""

import json
from types import SimpleNamespace as NS

from app.agent import TOOLS
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ToolCall
from app.llm.openai_provider import OpenAIProvider

HISTORY = [
    {"role": "user", "content": "Sender: a@b.com"},
    {"role": "assistant", "text": None, "tool_calls": [
        ToolCall("c1", "get_customer_history", {"email": "a@b.com"}),
        ToolCall("c2", "search_similar_tickets", {"query": "refund"}),
    ]},
    {"role": "tool", "tool_call_id": "c1", "name": "get_customer_history", "content": '{"tickets": []}'},
    {"role": "tool", "tool_call_id": "c2", "name": "search_similar_tickets", "content": '{"tickets": []}'},
]


class Recorder:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_openai_request_and_response_mapping():
    response = NS(choices=[NS(message=NS(content=None, tool_calls=[
        NS(id="t1", function=NS(name="submit_triage", arguments='{"category": "billing"}')),
        NS(id="t2", function=NS(name="submit_triage", arguments='{"category": ')),  # truncated JSON
    ]))])
    rec = Recorder(response)
    provider = OpenAIProvider("gpt-4o-mini", client=NS(chat=NS(completions=rec)))

    turn = provider.complete("system prompt", HISTORY, TOOLS)

    sent = rec.kwargs
    assert sent["tool_choice"] == "required"
    assert sent["messages"][0] == {"role": "system", "content": "system prompt"}
    assert json.loads(sent["messages"][2]["tool_calls"][0]["function"]["arguments"]) == {"email": "a@b.com"}
    assert [m["role"] for m in sent["messages"]] == ["system", "user", "assistant", "tool", "tool"]
    assert {t["function"]["name"] for t in sent["tools"]} == {"get_customer_history", "search_similar_tickets", "submit_triage"}

    assert turn.tool_calls[0].arguments == {"category": "billing"}
    assert turn.tool_calls[1].parse_error is not None


def test_anthropic_groups_tool_results_into_one_user_message():
    response = NS(content=[
        NS(type="text", text="Looking at history."),
        NS(type="tool_use", id="tu1", name="submit_triage", input={"category": "billing"}),
    ])
    rec = Recorder(response)
    provider = AnthropicProvider("claude-haiku-4-5", client=NS(messages=rec))

    turn = provider.complete("system prompt", HISTORY, TOOLS)

    sent = rec.kwargs
    assert sent["system"] == "system prompt"
    assert sent["tool_choice"] == {"type": "any"}
    assert [m["role"] for m in sent["messages"]] == ["user", "assistant", "user"]
    results = sent["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["c1", "c2"]
    assert sent["messages"][1]["content"][0] == {
        "type": "tool_use", "id": "c1", "name": "get_customer_history", "input": {"email": "a@b.com"},
    }
    assert "input_schema" in sent["tools"][0]

    assert turn.text == "Looking at history."
    assert turn.tool_calls[0].name == "submit_triage"
