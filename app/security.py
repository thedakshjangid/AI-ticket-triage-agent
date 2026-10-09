"""Webhook signature checks (HMAC-SHA256) and API-key auth for the read endpoints."""

import hashlib
import hmac
import time

from fastapi import Header, HTTPException, status

from app.config import get_settings


def sign(body: bytes, timestamp: str, secret: str) -> str:
    """Signature = hex(HMAC-SHA256(secret, "<timestamp>.<raw body>")). Senders use the same function."""
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, timestamp: str | None, signature: str | None, now: float | None = None) -> None:
    settings = get_settings()
    if not timestamp or not signature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-Timestamp or X-Signature header")
    try:
        ts = int(timestamp)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid X-Timestamp header")
    # Reject old requests so a captured request can't be replayed later.
    if abs((now or time.time()) - ts) > settings.signature_tolerance_seconds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Request timestamp outside allowed window")
    expected = sign(body, timestamp, settings.webhook_secret)
    if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not x_api_key or not hmac.compare_digest(x_api_key, get_settings().api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid X-API-Key")
