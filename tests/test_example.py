"""End-to-end: the example app runs with no provider and still works offline."""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}{(' -> ' + detail) if detail and not condition else ''}")
    return condition


results = []

with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(ROOT, "scripts")
    proc = subprocess.run([sys.executable, os.path.join(ROOT, "examples", "hello_local_ai.py")],
                          capture_output=True, text=True, cwd=tmp, env=env, timeout=60)
    out = proc.stdout + proc.stderr
    results.append(check("example exits 0", proc.returncode == 0, out[-400:]))
    results.append(check("reports the provider state", "Provider:" in out, out[:200]))
    results.append(check("uses the offline answer", "offline default" in out, out[-400:]))
    results.append(check("writes a local ledger", os.path.exists(os.path.join(tmp, "state.json"))))
    if os.path.exists(os.path.join(tmp, "state.json")):
        with open(os.path.join(tmp, "state.json"), encoding="utf-8") as fh:
            state = json.load(fh)
        results.append(check("ledger has the answer", len(state.get("answers", [])) == 1, str(state)))
        results.append(check("ledger records the provider", "provider" in state["answers"][0], str(state)))

print()
print(f"{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
