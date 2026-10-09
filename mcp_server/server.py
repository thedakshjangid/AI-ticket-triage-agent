"""MCP server that lets an AI assistant (Claude Desktop, Cursor, etc.) work with the ticket queue.

Run:  python -m mcp_server.server          (stdio, for Claude Desktop)
      MCP_TRANSPORT=streamable-http python -m mcp_server.server
"""

import os
from typing import Literal

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, select

from app.db import Ticket, get_sessionmaker

mcp = FastMCP("ticket-triage")

Status = Literal["received", "triaged", "needs_review", "triage_failed", "resolved"]
Priority = Literal["low", "medium", "high", "urgent"]


def _compact(t: Ticket) -> dict:
    return {
        "id": t.id,
        "subject": t.subject,
        "sender_email": t.sender_email,
        "status": t.status,
        "category": t.category,
        "priority": t.priority,
        "needs_human": t.needs_human,
        "summary": t.summary,
    }


@mcp.tool()
def list_tickets(status: Status | None = None, priority: Priority | None = None, limit: int = 20) -> list[dict]:
    """List recent tickets, newest first. Filter by status and/or priority."""
    with get_sessionmaker()() as session:
        query = select(Ticket).order_by(Ticket.created_at.desc()).limit(min(max(limit, 1), 100))
        if status:
            query = query.where(Ticket.status == status)
        if priority:
            query = query.where(Ticket.priority == priority)
        return [_compact(t) for t in session.scalars(query).all()]


@mcp.tool()
def get_ticket(ticket_id: int) -> dict:
    """Get one ticket in full: the original message, the triage decision, the suggested reply and the agent's tool calls."""
    with get_sessionmaker()() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        return ticket.to_dict()


@mcp.tool()
def update_ticket_status(ticket_id: int, status: Status) -> dict:
    """Change a ticket's status, for example to 'resolved' after replying to the customer."""
    with get_sessionmaker()() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} not found")
        ticket.status = status
        session.commit()
        return _compact(ticket)


@mcp.tool()
def ticket_stats() -> dict:
    """Count tickets by status and by priority, for a quick view of the queue."""
    with get_sessionmaker()() as session:
        by_status = dict(session.execute(select(Ticket.status, func.count()).group_by(Ticket.status)).all())
        by_priority = dict(
            session.execute(
                select(Ticket.priority, func.count()).where(Ticket.priority.is_not(None)).group_by(Ticket.priority)
            ).all()
        )
        return {"by_status": by_status, "by_priority": by_priority}


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
