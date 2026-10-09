"""FastAPI service: signed webhook in, triaged tickets out."""

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import triage_ticket
from app.db import Ticket, get_session, get_sessionmaker
from app.llm import LLMProvider, get_provider
from app.schemas import InboundMessage, StatusUpdate
from app.security import require_api_key, verify_signature


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_sessionmaker()  # creates the engine and tables on first start
    yield


app = FastAPI(title="AI Ticket Triage Agent", version="1.0.0", lifespan=lifespan)


def get_llm_provider() -> LLMProvider:
    return get_provider()


def run_triage_job(ticket_id: int, provider: LLMProvider) -> None:
    """Runs after the webhook has responded, with its own DB session."""
    session = get_sessionmaker()()
    try:
        ticket = session.get(Ticket, ticket_id)
        if ticket is not None:
            triage_ticket(session, ticket, provider)
    finally:
        session.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/inbound", status_code=status.HTTP_202_ACCEPTED)
async def inbound_webhook(
    request: Request,
    background: BackgroundTasks,
    x_timestamp: str | None = Header(default=None),
    x_signature: str | None = Header(default=None),
    session: Session = Depends(get_session),
    provider: LLMProvider = Depends(get_llm_provider),
):
    raw = await request.body()
    verify_signature(raw, x_timestamp, x_signature)  # check the raw bytes before parsing anything
    try:
        msg = InboundMessage.model_validate_json(raw)
    except ValidationError as e:
        raise HTTPException(422, e.errors(include_url=False, include_context=False, include_input=False))

    existing = session.scalar(select(Ticket).where(Ticket.external_id == msg.external_id))
    if existing:
        # Senders retry on timeouts; the same message must not create a second ticket.
        return JSONResponse({"ticket_id": existing.id, "status": existing.status, "duplicate": True}, status_code=200)

    ticket = Ticket(
        external_id=msg.external_id,
        source=msg.source,
        sender_email=str(msg.sender_email).lower(),
        subject=msg.subject.strip(),
        body=msg.body,
        status="received",
    )
    session.add(ticket)
    try:
        session.commit()
    except IntegrityError:
        # Two copies of the same message arrived at the same moment; the other one won.
        session.rollback()
        existing = session.scalar(select(Ticket).where(Ticket.external_id == msg.external_id))
        return JSONResponse({"ticket_id": existing.id, "status": existing.status, "duplicate": True}, status_code=200)

    background.add_task(run_triage_job, ticket.id, provider)
    return {"ticket_id": ticket.id, "status": "received", "duplicate": False}


@app.get("/tickets", dependencies=[Depends(require_api_key)])
def list_tickets(
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    query = select(Ticket).order_by(Ticket.created_at.desc()).limit(min(max(limit, 1), 200))
    if status_filter:
        query = query.where(Ticket.status == status_filter)
    if priority:
        query = query.where(Ticket.priority == priority)
    return [t.to_dict() for t in session.scalars(query).all()]


@app.get("/tickets/stats", dependencies=[Depends(require_api_key)])
def ticket_stats(session: Session = Depends(get_session)):
    by_status = dict(session.execute(select(Ticket.status, func.count()).group_by(Ticket.status)).all())
    by_priority = dict(
        session.execute(
            select(Ticket.priority, func.count()).where(Ticket.priority.is_not(None)).group_by(Ticket.priority)
        ).all()
    )
    return {"by_status": by_status, "by_priority": by_priority}


@app.get("/tickets/{ticket_id}", dependencies=[Depends(require_api_key)])
def get_ticket(ticket_id: int, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket.to_dict()


@app.patch("/tickets/{ticket_id}", dependencies=[Depends(require_api_key)])
def update_ticket(ticket_id: int, update: StatusUpdate, session: Session = Depends(get_session)):
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    ticket.status = update.status
    session.commit()
    return ticket.to_dict()


@app.post("/tickets/{ticket_id}/retriage", dependencies=[Depends(require_api_key)])
def retriage(ticket_id: int, session: Session = Depends(get_session), provider: LLMProvider = Depends(get_llm_provider)):
    """Re-run the agent, e.g. after a provider outage left a ticket in triage_failed."""
    ticket = session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return triage_ticket(session, ticket, provider).to_dict()
