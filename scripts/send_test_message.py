"""Send a signed test message to the webhook, the same way n8n or any other sender would.

    python scripts/send_test_message.py "My card was charged twice" --email priya@example.com
    python scripts/send_test_message.py "Same message" --external-id demo-1   # run twice to see duplicate handling
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.security import sign  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("body")
    parser.add_argument("--subject", default="Test message")
    parser.add_argument("--email", default="customer@example.com")
    parser.add_argument("--external-id", default=None, help="Reuse an ID to test duplicate handling")
    parser.add_argument("--url", default=os.getenv("TRIAGE_URL", "http://localhost:8000/webhooks/inbound"))
    parser.add_argument("--secret", default=os.getenv("WEBHOOK_SECRET", "dev-webhook-secret"))
    args = parser.parse_args()

    payload = {
        "external_id": args.external_id or f"cli-{uuid.uuid4()}",
        "sender_email": args.email,
        "subject": args.subject,
        "body": args.body,
        "source": "cli",
    }
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    headers = {"Content-Type": "application/json", "X-Timestamp": ts, "X-Signature": "sha256=" + sign(body, ts, args.secret)}
    resp = httpx.post(args.url, content=body, headers=headers, timeout=10)
    print(resp.status_code, resp.text)


if __name__ == "__main__":
    main()
