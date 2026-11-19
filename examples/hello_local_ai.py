"""Smallest complete local-first AI app, using the toolkit.

Run:
    python examples/hello_local_ai.py

It:
  1. reads the provider from .env (run scripts/setup_provider.py first)
  2. asks the AI for a JSON answer
  3. falls back to a deterministic offline answer if the AI is unreachable
  4. keeps the result in a local ledger (state.json)

Everything here is stdlib. No pip install.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from local_ai import LocalAI, safe_json          # noqa: E402
from ledger import Ledger                        # noqa: E402


def offline_answer():
    """The deterministic path. This is what makes the app local-first:
    the AI is an enhancement, never a single point of failure."""
    return {"city": "Mumbai", "reason": "offline default - no provider answer", "confident": False}


def main():
    db = Ledger("state.json", default={"answers": []})

    ai = LocalAI()
    print(f"Provider: {ai.describe()}")

    prompt = ("You are a weather triage helper. The user is in India. "
              "Reply with JSON: {\"city\": \"...\", \"monsoon\": true|false, "
              "\"reason\": \"under 15 words\"}")

    answer = safe_json(ai, prompt, fallback=offline_answer, verbose=True)

    print("Answer:", answer)
    db.append("answers", {"provider": ai.describe(), **answer})
    print(f"Ledger: {db.path} ({len(db.get('answers', []))} entries)")


if __name__ == "__main__":
    main()
