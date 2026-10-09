"""Talk to the MCP server through a real MCP client session (in memory)."""

import json

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from app.db import Ticket
from mcp_server.server import mcp


@pytest.fixture
def seeded(session):
    session.add_all([
        Ticket(external_id="1", sender_email="a@x.com", subject="Site down", body="b", status="needs_review",
               category="technical_issue", priority="urgent", needs_human=True, summary="Outage"),
        Ticket(external_id="2", sender_email="b@x.com", subject="Idea", body="b", status="triaged",
               category="feature_request", priority="low", summary="CSV export idea"),
    ])
    session.commit()


def call(tool: str, args: dict | None = None):
    async def run():
        async with create_connected_server_and_client_session(mcp._mcp_server) as client:
            listed = await client.list_tools()
            result = await client.call_tool(tool, args or {})
            return [t.name for t in listed.tools], result

    return anyio.run(run)


def payload(result):
    if result.structuredContent is not None:
        data = result.structuredContent
        return data.get("result", data)
    return json.loads(result.content[0].text)


def test_tools_are_listed(seeded):
    names, _ = call("ticket_stats")
    assert set(names) == {"list_tickets", "get_ticket", "update_ticket_status", "ticket_stats"}


def test_list_filter_and_update(seeded):
    _, result = call("list_tickets", {"priority": "urgent"})
    tickets = payload(result)
    assert [t["subject"] for t in tickets] == ["Site down"]

    _, result = call("update_ticket_status", {"ticket_id": tickets[0]["id"], "status": "resolved"})
    assert payload(result)["status"] == "resolved"

    _, result = call("ticket_stats")
    assert payload(result)["by_status"] == {"resolved": 1, "triaged": 1}


def test_invalid_status_and_missing_ticket_are_errors(seeded):
    _, result = call("update_ticket_status", {"ticket_id": 1, "status": "deleted"})
    assert result.isError
    _, result = call("get_ticket", {"ticket_id": 999})
    assert result.isError
