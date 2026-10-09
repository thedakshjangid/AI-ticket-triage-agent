import json
import time

from app.llm.mock_provider import MockProvider
from tests.conftest import FailingProvider, auth, make_payload, post_message, signed_headers


def test_signed_message_is_stored_and_triaged(client):
    resp = post_message(client, make_payload())
    assert resp.status_code == 202
    ticket_id = resp.json()["ticket_id"]

    ticket = client.get(f"/tickets/{ticket_id}", headers=auth()).json()
    assert ticket["sender_email"] == "priya@example.com"  # normalised
    assert ticket["category"] == "billing"
    assert ticket["priority"] == "high"  # "charged twice"
    assert ticket["status"] == "needs_review"
    assert [step["tool"] for step in ticket["agent_trace"]] == ["get_customer_history", "submit_triage"]


def test_invalid_signature_rejected(client):
    body = json.dumps(make_payload()).encode()
    headers = signed_headers(body, secret="wrong-secret")
    assert client.post("/webhooks/inbound", content=body, headers=headers).status_code == 401


def test_tampered_body_rejected(client):
    body = json.dumps(make_payload()).encode()
    headers = signed_headers(body)
    tampered = body.replace(b"twice", b"once!")
    assert client.post("/webhooks/inbound", content=tampered, headers=headers).status_code == 401


def test_missing_signature_headers_rejected(client):
    resp = client.post("/webhooks/inbound", json=make_payload())
    assert resp.status_code == 401


def test_replayed_old_request_rejected(client):
    resp = post_message(client, make_payload(), timestamp=int(time.time()) - 3600)
    assert resp.status_code == 401
    assert "window" in resp.json()["detail"]


def test_duplicate_delivery_is_idempotent(client):
    first = post_message(client, make_payload())
    second = post_message(client, make_payload())
    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["ticket_id"] == first.json()["ticket_id"]
    assert len(client.get("/tickets", headers=auth()).json()) == 1


def test_invalid_payloads_rejected(client):
    assert post_message(client, make_payload(body="   ")).status_code == 422
    assert post_message(client, make_payload(sender_email="not-an-email")).status_code == 422
    payload = make_payload()
    del payload["external_id"]
    assert post_message(client, payload).status_code == 422


def test_non_json_body_rejected(client):
    body = b"this is not json"
    assert client.post("/webhooks/inbound", content=body, headers=signed_headers(body)).status_code == 422


def test_read_endpoints_need_api_key(client):
    assert client.get("/tickets").status_code == 401
    assert client.get("/tickets", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/tickets", headers=auth()).status_code == 200


def test_provider_failure_is_recorded_then_retriage_works(client, provider_holder):
    provider_holder["provider"] = FailingProvider()
    ticket_id = post_message(client, make_payload()).json()["ticket_id"]

    ticket = client.get(f"/tickets/{ticket_id}", headers=auth()).json()
    assert ticket["status"] == "triage_failed"
    assert "timed out" in ticket["triage_error"]

    provider_holder["provider"] = MockProvider()
    retried = client.post(f"/tickets/{ticket_id}/retriage", headers=auth()).json()
    assert retried["status"] == "needs_review"
    assert retried["triage_error"] is None


def test_filters_status_update_and_stats(client):
    post_message(client, make_payload(external_id="a"))
    post_message(
        client,
        make_payload(external_id="b", subject="Idea", body="Would be great to export reports as CSV."),
    )
    low = client.get("/tickets", params={"priority": "low"}, headers=auth()).json()
    assert [t["external_id"] for t in low] == ["b"]

    updated = client.patch(f"/tickets/{low[0]['id']}", json={"status": "resolved"}, headers=auth())
    assert updated.json()["status"] == "resolved"
    assert client.patch(f"/tickets/{low[0]['id']}", json={"status": "deleted"}, headers=auth()).status_code == 422

    stats = client.get("/tickets/stats", headers=auth()).json()
    assert stats["by_status"] == {"needs_review": 1, "resolved": 1}


def test_unknown_ticket_404(client):
    assert client.get("/tickets/999", headers=auth()).status_code == 404
