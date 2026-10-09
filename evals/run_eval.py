"""Score a provider against the hand-labelled golden set.

    python -m evals.run_eval                    # offline keyword baseline
    python -m evals.run_eval --provider openai  # needs OPENAI_API_KEY
    python -m evals.run_eval --provider anthropic

Each case runs through the real agent loop against a throwaway SQLite database.
"""

import argparse
import json
import time
from pathlib import Path

from app import db
from app.agent import AgentError, run_agent
from app.db import Ticket
from app.llm import get_provider

PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "urgent": 3}
HERE = Path(__file__).parent


def evaluate(provider_name: str, cases_path: Path) -> dict:
    cases = [json.loads(line) for line in cases_path.read_text().splitlines() if line.strip()]
    provider = get_provider(provider_name)
    rows = []

    for case in cases:
        db.init_engine("sqlite://")  # fresh in-memory DB per case
        session = db.get_sessionmaker()()
        ticket = Ticket(external_id=case["id"], sender_email="eval@example.com", subject=case["subject"], body=case["body"])
        session.add(ticket)
        session.commit()

        started = time.perf_counter()
        try:
            outcome = run_agent(session, ticket, provider)
            got = outcome.result.model_dump()
            error, tool_calls, retries = None, len(outcome.trace), outcome.validation_retries
        except (AgentError, Exception) as e:
            got, error, tool_calls, retries = {}, f"{type(e).__name__}: {e}", 0, 0
        latency = time.perf_counter() - started
        session.close()

        exp = case["expected"]
        rows.append({
            "id": case["id"],
            "expected": exp,
            "got": {k: got.get(k) for k in ("category", "priority", "needs_human")},
            "category_ok": got.get("category") == exp["category"],
            "priority_ok": got.get("priority") == exp["priority"],
            "priority_within_one": got.get("priority") in PRIORITY_RANK
            and abs(PRIORITY_RANK[got["priority"]] - PRIORITY_RANK[exp["priority"]]) <= 1,
            "needs_human_ok": got.get("needs_human") == exp["needs_human"],
            "tool_calls": tool_calls,
            "validation_retries": retries,
            "latency_s": round(latency, 3),
            "error": error,
        })

    n = len(rows)
    pct = lambda key: round(100 * sum(r[key] for r in rows) / n, 1)
    return {
        "provider": provider.name,
        "cases": n,
        "category_accuracy": pct("category_ok"),
        "priority_exact": pct("priority_ok"),
        "priority_within_one_level": pct("priority_within_one"),
        "needs_human_accuracy": pct("needs_human_ok"),
        "failures": sum(1 for r in rows if r["error"]),
        "avg_tool_calls": round(sum(r["tool_calls"] for r in rows) / n, 2),
        "avg_latency_s": round(sum(r["latency_s"] for r in rows) / n, 3),
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="mock", choices=["mock", "openai", "anthropic"])
    parser.add_argument("--cases", default=str(HERE / "golden_set.jsonl"))
    parser.add_argument("--out", default=None, help="Write full results JSON here")
    args = parser.parse_args()

    report = evaluate(args.provider, Path(args.cases))
    print(f"Provider: {report['provider']}  ({report['cases']} cases)")
    for key in ("category_accuracy", "priority_exact", "priority_within_one_level", "needs_human_accuracy"):
        print(f"  {key:<28} {report[key]:>5}%")
    print(f"  {'failures':<28} {report['failures']:>5}")
    print(f"  {'avg_tool_calls':<28} {report['avg_tool_calls']:>5}")
    print("\nMisses:")
    for r in report["rows"]:
        if not (r["category_ok"] and r["priority_ok"] and r["needs_human_ok"]):
            print(f"  {r['id']}: expected {r['expected']} got {r['got']}" + (f"  [{r['error']}]" if r["error"] else ""))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
