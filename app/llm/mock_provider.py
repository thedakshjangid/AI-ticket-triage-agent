"""Offline keyword-based provider.

It follows the same tool-calling protocol as the real models (look up history, then submit),
so the whole pipeline (webhook, agent loop, database, MCP) runs and is tested without an API key.
It is also the baseline the eval script compares real models against.
"""

import json
import re
import uuid

from app.llm.base import LLMTurn, ToolCall, ToolSpec

URGENT = ["outage", "is down", "site down", "production", "data breach", "hacked", "urgent", "asap", "all users"]
RULES = [
    ("account_access", ["password", "login", "log in", "locked out", "2fa", "two-factor", "reset link", "sign in"]),
    ("billing", ["invoice", "charged", "refund", "payment", "billing", "subscription", "receipt", "card"]),
    ("complaint", ["disappointed", "unacceptable", "terrible", "complaint", "worst", "frustrated"]),
    ("feature_request", ["feature", "would be great", "could you add", "suggestion", "would love", "wish"]),
    ("technical_issue", ["error", "bug", "crash", "not working", "broken", "500", "timeout", "fails", "slow"]),
]


def classify(text: str) -> tuple[str, str]:
    t = text.lower()
    category = next((cat for cat, words in RULES if any(w in t for w in words)), "other")
    if any(w in t for w in URGENT):
        priority = "urgent"
    elif category == "complaint" or "twice" in t or "double" in t:
        priority = "high"
    elif category == "feature_request" or category == "other":
        priority = "low"
    else:
        priority = "medium"
    return category, priority


class MockProvider:
    name = "mock"

    def complete(self, system: str, messages: list[dict], tools: list[ToolSpec]) -> LLMTurn:
        first = messages[0]["content"]
        tool_results = [m for m in messages if m["role"] == "tool"]

        if not tool_results:
            match = re.search(r"Sender:\s*(\S+@\S+)", first)
            email = match.group(1) if match else ""
            return LLMTurn(tool_calls=[ToolCall(f"mock_{uuid.uuid4().hex[:8]}", "get_customer_history", {"email": email})])

        history = []
        try:
            history = json.loads(tool_results[0]["content"]).get("tickets", [])
        except (json.JSONDecodeError, AttributeError):
            pass

        body = first.split("<customer_message>")[-1].split("</customer_message>")[0]
        category, priority = classify(body)
        subject = re.search(r"Subject:\s*(.*)", first)
        summary = (subject.group(1).strip() if subject and subject.group(1).strip() else body.strip()[:120]) or "Customer message"
        args = {
            "category": category,
            "priority": priority,
            "summary": f"{category.replace('_', ' ').title()}: {summary}"[:400],
            "suggested_reply": "Thanks for reaching out. We've logged your request and a member of our team will follow up shortly.",
            "needs_human": priority in ("high", "urgent") or len(history) >= 2,
            "reasoning": f"Keyword match; {len(history)} previous ticket(s) from this sender.",
        }
        return LLMTurn(tool_calls=[ToolCall(f"mock_{uuid.uuid4().hex[:8]}", "submit_triage", args)])
