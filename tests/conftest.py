import json
import os
import time

# Settings are read once, so set them before the app is imported.
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("LLM_PROVIDER", "mock")

import pytest
from fastapi.testclient import TestClient

from app import db
from app.llm.base import LLMTurn
from app.llm.mock_provider import MockProvider
from app.main import app, get_llm_provider
from app.security import sign

SECRET = os.environ["WEBHOOK_SECRET"]
API_KEY = os.environ["API_KEY"]


@pytest.fixture
def database(tmp_path):
    """SQLite by default; set TEST_DATABASE_URL to run the same tests against PostgreSQL."""
    url = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    engine = db.init_engine(url)
    if not url.startswith("sqlite"):
        db.Base.metadata.drop_all(engine)
        db.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(database):
    s = db.get_sessionmaker()()
    yield s
    s.close()


class ScriptedProvider:
    """Returns pre-written turns in order and records what it was sent."""

    name = "scripted"

    def __init__(self, turns: list[LLMTurn]):
        self.turns = list(turns)
        self.calls: list[list[dict]] = []

    def complete(self, system, messages, tools):
        self.calls.append([dict(m) for m in messages])
        if not self.turns:
            raise AssertionError("ScriptedProvider ran out of turns")
        return self.turns.pop(0)


class FailingProvider:
    name = "failing"

    def complete(self, system, messages, tools):
        raise TimeoutError("LLM provider timed out")


@pytest.fixture
def provider_holder():
    return {"provider": MockProvider()}


@pytest.fixture
def client(database, provider_holder):
    app.dependency_overrides[get_llm_provider] = lambda: provider_holder["provider"]
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def signed_headers(body: bytes, timestamp: int | None = None, secret: str = SECRET) -> dict:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    return {"X-Timestamp": ts, "X-Signature": "sha256=" + sign(body, ts, secret), "Content-Type": "application/json"}


def post_message(client, payload: dict, **kwargs):
    body = json.dumps(payload).encode()
    return client.post("/webhooks/inbound", content=body, headers=signed_headers(body, **kwargs))


def make_payload(**overrides) -> dict:
    payload = {
        "external_id": "msg-001",
        "sender_email": "Priya@Example.com",
        "subject": "Charged twice this month",
        "body": "Hi, I was charged twice for my subscription in September. Can you check the invoice?",
        "source": "email",
    }
    payload.update(overrides)
    return payload


def auth():
    return {"X-API-Key": API_KEY}
