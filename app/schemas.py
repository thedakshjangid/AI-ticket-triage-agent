"""Request and LLM-output schemas. Pydantic does the validation, so bad data is rejected at the edge."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

Category = Literal["billing", "technical_issue", "account_access", "feature_request", "complaint", "other"]
Priority = Literal["low", "medium", "high", "urgent"]
TicketStatus = Literal["received", "triaged", "needs_review", "triage_failed", "resolved"]


class InboundMessage(BaseModel):
    """Payload the webhook accepts. n8n (or any other system) normalises messages into this shape."""

    external_id: str = Field(min_length=1, max_length=255)
    sender_email: EmailStr
    subject: str = Field(default="", max_length=500)
    body: str = Field(min_length=1, max_length=50_000)
    source: str = Field(default="webhook", max_length=50)

    @field_validator("body")
    @classmethod
    def body_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("body must not be blank")
        return v


class TriageResult(BaseModel):
    """Structured output the agent must produce. Anything that doesn't fit is sent back to the model."""

    category: Category
    priority: Priority
    summary: str = Field(min_length=5, max_length=400)
    suggested_reply: str = Field(min_length=5, max_length=2000)
    needs_human: bool
    reasoning: str = Field(default="", max_length=600)


class StatusUpdate(BaseModel):
    status: TicketStatus
