"""Tests for local_ai.py against a fake OpenAI-compatible server."""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from local_ai import LocalAI, parse_json, safe_complete, safe_json  # noqa: E402

REQUESTS = []


class Handler(BaseHTTPRequestHandler):
    reject = set()

    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        REQUESTS.append(json.loads(raw) if raw else {})
        payload = json.loads(raw) if raw else {}

        if "max_tokens" in payload and "max_tokens" in self.reject:
            self._send(400, {"error": "unsupported parameter: max_tokens"})
            return
        if "response_format" in payload and "response_format" in self.reject:
            self._send(400, {"error": "response_format is not supported"})
            return
        if "reasoning_effort" in payload and "reasoning_effort" in self.reject:
            self._send(400, {"error": "unknown parameter: reasoning"})
            return
        if payload.get("model") == "bad-key-model":
            self._send(401, {"error": "invalid api key"})
            return
        content = '{"city": "Mumbai", "monsoon": true}' if payload.get("model") == "json-model" else "pong"
        self._send(200, {"choices": [{"message": {"role": "assistant", "content": content}}],
                         "model": payload.get("model", "?")})


def start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}{(' -> ' + detail) if detail and not condition else ''}")
    return condition


results = []
server, base = start_server()
try:
    # 1. configuration from explicit args
    ai = LocalAI(base_url=base, api_key="sk-test", model="test-model")
    results.append(check("configured", ai.configured))
    results.append(check("describe names provider", "127.0.0.1" in ai.describe(), ai.describe()))

    # 2. not configured -> safe_* use the fallback
    empty = LocalAI(base_url="", api_key="", model="")
    results.append(check("empty client is not configured", not empty.configured))
    results.append(check("safe_complete falls back when unconfigured",
                         safe_complete(empty, "x", fallback=lambda: "offline") == "offline"))

    # 2b. keyless local provider (Ollama / LM Studio / vLLM) is usable
    keyless = LocalAI(base_url=base, api_key="", model="test-model", env_file=None)
    results.append(check("keyless provider is configured", keyless.configured))
    results.append(check("keyless provider completes", safe_complete(keyless, "ping", fallback=lambda: "offline") == "pong"))

    # 3. plain completion
    ai = LocalAI(base_url=base, api_key="sk-test", model="test-model")
    results.append(check("complete returns text", ai.complete("ping") == "pong", repr(ai.complete("ping"))))

    # 4. json parsing
    results.append(check("parse_json plain", parse_json('{"a": 1}') == {"a": 1}))
    results.append(check("parse_json fenced", parse_json('```json\n{"a": 2}\n```') == {"a": 2}))
    results.append(check("parse_json with prose", parse_json('here you go: {"a": 3} hope that helps') == {"a": 3}))
    try:
        parse_json("no json here")
        results.append(check("parse_json rejects junk", False))
    except ValueError:
        results.append(check("parse_json rejects junk", True))

    # 5. safe_json returns the parsed object for a JSON-capable model
    ai = LocalAI(base_url=base, api_key="sk-test", model="json-model")
    parsed = safe_json(ai, "x", fallback=lambda: {"fallback": True})
    results.append(check("safe_json parses", parsed == {"city": "Mumbai", "monsoon": True}, str(parsed)))

    # 5b. a non-JSON reply falls back instead of crashing
    ai_text = LocalAI(base_url=base, api_key="sk-test", model="test-model")
    results.append(check("non-JSON reply -> fallback",
                         safe_json(ai_text, "x", fallback=lambda: {"fallback": True}) == {"fallback": True}))

    # 6. max_tokens rejection -> retried with max_completion_tokens
    Handler.reject = {"max_tokens"}
    REQUESTS.clear()
    ai = LocalAI(base_url=base, api_key="sk-test", model="test-model")
    text = ai.complete("ping")
    results.append(check("max_tokens rejection handled", text == "pong"))
    results.append(check("swapped to max_completion_tokens",
                         any("max_completion_tokens" in r for r in REQUESTS), str(REQUESTS)))
    results.append(check("no duplicate payloads",
                         len({json.dumps(r, sort_keys=True) for r in REQUESTS}) == len(REQUESTS), str(REQUESTS)))
    Handler.reject = set()

    # 7. auth failure is not retried
    Handler.reject = set()
    REQUESTS.clear()
    ai = LocalAI(base_url=base, api_key="sk-test", model="bad-key-model")
    try:
        ai.complete("ping")
        results.append(check("401 raises", False))
    except Exception:
        results.append(check("401 raises", True))
    results.append(check("401 not retried", len(REQUESTS) == 1, str(len(REQUESTS))))

    # 8. dead provider -> fallback, no crash
    dead = LocalAI(base_url="http://127.0.0.1:1/v1", api_key="sk-test", model="m")
    results.append(check("dead provider -> fallback",
                         safe_complete(dead, "x", fallback=lambda: "offline") == "offline"))
    results.append(check("dead provider -> json fallback",
                         safe_json(dead, "x", fallback=lambda: {"offline": True}) == {"offline": True}))

    # 9. config read from .env
    with tempfile.TemporaryDirectory() as tmp:
        env_path = os.path.join(tmp, ".env")
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write("AI_BASE_URL=http://example.invalid/v1\nAI_API_KEY=sk-env\nAI_MODEL=env-model\n")
        from_env = LocalAI(env_file=env_path)
        results.append(check("reads base url from .env", from_env.base_url == "http://example.invalid/v1"))
        results.append(check("reads model from .env", from_env.model == "env-model"))
        results.append(check("env key present", bool(from_env.api_key)))

    # 10. nonexistent env file is not an error
    missing = LocalAI(env_file=os.path.join(tmp, "nope.env"))
    results.append(check("missing .env tolerated", not missing.configured))
finally:
    server.shutdown()

print()
print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
