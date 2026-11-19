"""Tests for setup_provider.py: model parsing, endpoint fallback, presets, .env."""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import setup_provider  # noqa: E402
from envfile import load_env, save_env  # noqa: E402

REQUESTS = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        REQUESTS.append(("GET", self.path, self.headers.get("Authorization")))
        if self.path.endswith("/models"):
            self._send(200, {"object": "list", "data": [
                {"id": "alpha-fast"}, {"id": "beta-good"}, {"id": "gamma-cheap"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        REQUESTS.append(("POST", self.path, self.headers.get("Authorization")))
        if self.path.endswith("/chat/completions"):
            payload = json.loads(raw) if raw else {}
            if payload.get("model") == "new-openai-model" and "max_tokens" in payload:
                self._send(400, {"error": {"message": "Unsupported parameter: 'max_tokens'. "
                                                      "Use 'max_completion_tokens' instead."}})
                return
            self._send(200, {"choices": [{"message": {"role": "assistant", "content": "pong"}}],
                              "model": payload.get("model", "?")})
        else:
            self._send(404, {"error": "not found"})


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
    # 1. model listing
    models, used_base, error = setup_provider.fetch_models(base, "sk-test")
    results.append(check("model list fetched", models == ["alpha-fast", "beta-good", "gamma-cheap"], str(models)))
    results.append(check("base url kept", used_base == base, used_base))
    results.append(check("auth header sent", any(r[2] for r in REQUESTS if r[0] == "GET")))

    # 2. response shapes
    shapes = [
        ({"data": [{"id": "a"}, {"id": "b"}]}, ["a", "b"]),
        ({"object": "list", "data": [{"name": "c"}, {"id": "d"}]}, ["c", "d"]),
        ({"models": [{"name": "e"}, {"model": "f"}]}, ["e", "f"]),
        ({"data": ["g", "h"]}, ["g", "h"]),
        ([{"id": "i"}, {"id": "j"}], ["i", "j"]),
    ]
    for shape, expected in shapes:
        parsed = setup_provider.parse_models(shape)
        label = list(shape.keys()) if isinstance(shape, dict) else "bare list"
        results.append(check(f"parse {label}", parsed == expected, f"{parsed} != {expected}"))

    # 3. duplicates removed
    results.append(check("duplicates removed",
                         setup_provider.parse_models({"data": [{"id": "x"}, {"id": "x"}, {"id": "y"}]}) == ["x", "y"]))

    # 4. chat test
    ok, detail = setup_provider.test_model(base, "sk-test", "alpha-fast")
    results.append(check("chat test passes", ok, detail))
    ok, detail = setup_provider.test_model(base, "sk-test", "new-openai-model")
    results.append(check("chat test: max_tokens rejection retried", ok, detail))
    ok, detail = setup_provider.test_model("http://127.0.0.1:1/v1", "sk-test", "alpha-fast", timeout=3)
    results.append(check("unreachable reported", ok is False and detail != "", detail))

    # 5. bare base url -> /v1 appended
    models2, used2, _ = setup_provider.fetch_models(base[:-3], "sk-test")
    results.append(check("bare base resolved to /v1", models2 == ["alpha-fast", "beta-good", "gamma-cheap"], str(used2)))

    # 6. .env round trip
    with tempfile.TemporaryDirectory() as tmp:
        env_path = os.path.join(tmp, ".env")
        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write("# comment\nBINANCE_API_KEY=keepme\nAI_API_KEY=old\n")
        values = load_env(env_path)
        values.update({"AI_API_KEY": "sk-new", "AI_MODEL": "beta-good", "AI_BASE_URL": base})
        save_env(env_path, values)
        after = load_env(env_path)
        results.append(check("other keys preserved", after.get("BINANCE_API_KEY") == "keepme"))
        results.append(check("key updated", after.get("AI_API_KEY") == "sk-new"))
        results.append(check("comment preserved", "# comment" in open(env_path, encoding="utf-8").read()))

        with open(env_path, "w", encoding="utf-8") as fh:
            fh.write('AI_API_KEY="sk-quoted"\nAI_MODEL=\'m1\'\nexport AI_BASE_URL=http://x/v1\n')
        quoted = load_env(env_path)
        results.append(check(".env: quotes stripped", quoted.get("AI_API_KEY") == "sk-quoted"
                             and quoted.get("AI_MODEL") == "m1", str(quoted)))
        results.append(check(".env: export prefix", quoted.get("AI_BASE_URL") == "http://x/v1", str(quoted)))

    # 6b. interactive wizard, no --preset, Enter on the API key (local provider)
    wizard = os.path.join(ROOT, "scripts", "setup_provider.py")
    with tempfile.TemporaryDirectory() as tmp:
        env_path = os.path.join(tmp, ".env")
        answers = "\n".join([base, "", "1", "", ""]) + "\n"   # base url, empty key, model #1, effort, tokens
        proc = subprocess.run([sys.executable, wizard, "--env-file", env_path],
                              input=answers, capture_output=True, text=True, timeout=60)
        out = proc.stdout + proc.stderr
        results.append(check("wizard: empty key + no preset does not crash",
                             proc.returncode == 0 and "Traceback" not in out, out[-400:]))
        saved = load_env(env_path)
        results.append(check("wizard: saves the picked model", saved.get("AI_MODEL") == "alpha-fast", str(saved)))
        results.append(check("wizard: saves an empty key", saved.get("AI_API_KEY") == "", str(saved)))

    # 6c. wizard with stdin closed (curl | bash, CI) exits cleanly
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run([sys.executable, wizard, "--env-file", os.path.join(tmp, ".env")],
                              input="", capture_output=True, text=True, timeout=60)
        out = proc.stdout + proc.stderr
        results.append(check("wizard: closed stdin -> clean exit 1",
                             proc.returncode == 1 and "Traceback" not in out and "nothing saved" in out, out[-400:]))
        results.append(check("wizard: closed stdin writes no .env", not os.path.exists(os.path.join(tmp, ".env"))))
finally:
    server.shutdown()

# 7. providers.json is valid and useful
providers = setup_provider.load_providers()
results.append(check("providers.json loads", len(providers) >= 10, str(len(providers))))
ids = {p["id"] for p in providers}
results.append(check("has openai + ollama", {"openai", "ollama"} <= ids, str(ids)))
results.append(check("every provider has a base_url", all(p.get("base_url") for p in providers)))
results.append(check("every provider has an id + name", all(p.get("id") and p.get("name") for p in providers)))
results.append(check("local providers need no key",
                     all(not p.get("auth") for p in providers if "localhost" in p.get("base_url", ""))))

# 8. preset lookup
results.append(check("preset groq found", (setup_provider.find_provider(providers, "groq") or {}).get("base_url") == "https://api.groq.com/openai/v1"))
results.append(check("unknown preset returns None", setup_provider.find_provider(providers, "nope") is None))

# 9. --presets and --check run as CLIs
proc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "setup_provider.py"), "--presets"],
                      capture_output=True, text=True, cwd=ROOT)
results.append(check("--presets lists providers", proc.returncode == 0 and "openai" in proc.stdout.lower(), proc.stderr[-200:]))

proc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "setup_provider.py"), "--check"],
                      capture_output=True, text=True, cwd=ROOT)
results.append(check("--check runs", proc.returncode == 0 and "Base URL" in proc.stdout, proc.stderr[-200:]))

print()
print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
