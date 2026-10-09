"""Database models and session handling (PostgreSQL in Docker, SQLite for local runs and tests)."""

from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # ID from the source system (email Message-ID, form submission ID...). Unique so retries are idempotent.
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(50), default="webhook")
    sender_email: Mapped[str] = mapped_column(String(320), index=True)
    subject: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text)

    # received -> triaged | needs_review | triage_failed -> resolved
    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_human: Mapped[bool] = mapped_column(Boolean, default=False)
    triage_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Every tool call the agent made, kept for debugging and auditing.
    agent_trace: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    triaged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "external_id": self.external_id,
            "source": self.source,
            "sender_email": self.sender_email,
            "subject": self.subject,
            "body": self.body,
            "status": self.status,
            "category": self.category,
            "priority": self.priority,
            "summary": self.summary,
            "suggested_reply": self.suggested_reply,
            "needs_human": self.needs_human,
            "triage_error": self.triage_error,
            "llm_provider": self.llm_provider,
            "agent_trace": self.agent_trace or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "triaged_at": self.triaged_at.isoformat() if self.triaged_at else None,
        }


_engine = None
_SessionLocal: sessionmaker | None = None


def init_engine(database_url: str | None = None):
    """Create the engine and tables. Called on startup, and by tests with their own URL."""
    global _engine, _SessionLocal
    url = database_url or get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    Base.metadata.create_all(_engine)
    return _engine


def get_sessionmaker() -> sessionmaker:
    if _SessionLocal is None:
        init_engine()
    return _SessionLocal


def get_session() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
