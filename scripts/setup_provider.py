"""Interactive provider setup - any OpenAI-compatible endpoint.

    python setup_provider.py                 # wizard
    python setup_provider.py --presets       # list curated providers
    python setup_provider.py --preset groq   # prefill from providers.json
    python setup_provider.py --list-models --base-url ... --api-key ...
    python setup_provider.py --check

Asks for the base URL, the API key (hidden) and then shows that provider's live
model list so you can pick a model. Writes AI_BASE_URL / AI_API_KEY / AI_MODEL
into .env and verifies the model answers.

Stdlib only - runs before anything is installed.
"""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_PROVIDERS = os.path.join(ROOT, "providers.json")

from envfile import load_env, save_env, mask  # noqa: E402


# ----------------------------------------------------------------- providers
def load_providers(path=DEFAULT_PROVIDERS):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh).get("providers", [])
    except Exception:
        return []


def find_provider(providers, provider_id):
    for entry in providers:
        if entry.get("id") == provider_id:
            return entry
    return None


def list_presets(path=DEFAULT_PROVIDERS):
    providers = load_providers(path)
    print(f"{len(providers)} curated providers ({path}):\n")
    for entry in providers:
        auth = "key required" if entry.get("auth") else "no key"
        verified = "  [verified]" if entry.get("verified") else ""
        free = ""
        if entry.get("free_models"):
            free = "  free: " + ", ".join(entry["free_models"][:3])
        print(f"  {entry['id']:<16} {entry['name']:<28} {auth}{verified}{free}")
        print(f"  {'':<16} {entry['base_url']}")


# ----------------------------------------------------------------- http
def _request(url, key=None, payload=None, timeout=25):
    headers = {"Accept": "application/json", "User-Agent": "make-it-local"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        return exc.code, body
    except Exception as exc:
        return 0, str(exc)


def parse_models(payload):
    """Pull model ids out of the shapes different providers use."""
    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = payload.get("data")
        if not isinstance(raw, list):
            raw = payload.get("models")
        if not isinstance(raw, list):
            raw = []
    else:
        raw = []

    ids = []
    for item in raw:
        if isinstance(item, str):
            ids.append(item)
        elif isinstance(item, dict):
            for field in ("id", "name", "model", "slug"):
                value = item.get(field)
                if isinstance(value, str) and value:
                    ids.append(value)
                    break
    seen, unique = set(), []
    for model_id in ids:
        if model_id not in seen:
            seen.add(model_id)
            unique.append(model_id)
    return unique


def fetch_models(base_url, key):
    """Try <base>/models, then <base>/v1/models. Returns (models, base_used, error)."""
    base = (base_url or "").rstrip("/")
    candidates = [base]
    if not base.endswith("/v1") and "/v1" not in base:
        candidates.append(base + "/v1")

    last_error = None
    for candidate in candidates:
        status, body = _request(candidate + "/models", key)
        if status == 200:
            try:
                models = parse_models(json.loads(body))
            except Exception as exc:
                last_error = f"could not parse model list: {exc}"
                continue
            if models:
                return models, candidate, None
            last_error = "provider returned an empty model list"
            continue
        if status == 401:
            last_error = "401 unauthorized - check the API key"
            continue
        if status == 404:
            last_error = f"404 at {candidate}/models"
            continue
        last_error = f"HTTP {status}: {body[:180]}"
    return [], base, last_error


def test_model(base_url, key, model, timeout=45):
    payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 8}
    status, body = _request((base_url or "").rstrip("/") + "/chat/completions", key, payload, timeout=timeout)
    if status == 200:
        try:
            reply = json.loads(body)["choices"][0]["message"].get("content") or ""
            return True, f"model answered: {str(reply).strip()[:60]!r}"
        except Exception as exc:
            return True, f"provider accepted the call (could not parse reply: {exc})"
    if status == 401:
        return False, "401 unauthorized - the API key is wrong"
    if status == 403:
        return False, "403 forbidden - the key may not have access to this model"
    if status == 404:
        return False, f"404 - '{model}' not found on this provider"
    if status == 400:
        return False, f"400 - provider rejected the request: {body[:200]}"
    if status == 0:
        return False, f"network error: {body[:160]}"
    return False, f"HTTP {status}: {body[:200]}"


# ----------------------------------------------------------------- wizard
def secret_prompt(prompt):
    try:
        if sys.stdin.isatty():
            return getpass.getpass(prompt)
    except Exception:
        pass
    return input(prompt + " (echoed, no console): ")


def choose_model(models):
    if not models:
        return None
    filtered = models
    while True:
        if len(filtered) > 25:
            hint = input("Filter by text (Enter = show all): ").strip()
            if hint:
                needle = hint.lower()
                matches = [m for m in models if needle in m.lower()]
                if matches:
                    filtered = matches
                    print(f"  {len(filtered)} match(es)")
                else:
                    print("  no match, showing everything")
                    filtered = models
            else:
                filtered = models

        shown = filtered[:60]
        for idx, model_id in enumerate(shown, 1):
            print(f"  [{idx:>3}] {model_id}")
        if len(filtered) > len(shown):
            print(f"  ... {len(filtered) - len(shown)} more (narrow it with a filter)")

        answer = input("Pick a model (number, or type the model id): ").strip()
        if not answer:
            continue
        if answer.isdigit():
            index = int(answer)
            if 1 <= index <= len(shown):
                return shown[index - 1]
            print(f"  pick 1-{len(shown)}")
            continue
        return answer


def run_interactive(env_path, providers, preset=None):
    values = load_env(env_path)
    curated = find_provider(providers, preset) if preset else None

    print("=" * 64)
    print("AI provider setup - any OpenAI-compatible endpoint")
    print("=" * 64)
    if curated:
        print(f"Preset: {curated['name']}  ({curated['base_url']})")
        if curated.get("notes"):
            print(f"  {curated['notes']}")
        if curated.get("signup"):
            print(f"  Sign up: {curated['signup']}")

    current_base = curated["base_url"] if curated else (values.get("AI_BASE_URL") or "https://api.openai.com/v1")
    current_model = values.get("AI_MODEL") or "gpt-4o-mini"
    print(f"\nCurrent: base={values.get('AI_BASE_URL') or '(none)'}  "
          f"model={values.get('AI_MODEL') or '(none)'}  key={mask(values.get('AI_API_KEY'))}")

    base_url = input(f"\nBase URL [{current_base}]: ").strip() or current_base
    base_url = base_url.rstrip("/")

    key = secret_prompt("API key (hidden, Enter = keep current): ").strip()
    if not key:
        key = values.get("AI_API_KEY", "")
    if not key and not curated.get("auth") is False:
        print("No API key given. Local providers (Ollama, LM Studio) need none - press Enter to continue.")
        key = values.get("AI_API_KEY", "")

    print(f"\nFetching model list from {base_url}/models ...")
    models, used_base, error = fetch_models(base_url, key)
    if models:
        print(f"OK - {len(models)} model(s) found.")
        base_url = used_base
    else:
        print(f"Could not list models ({error}).")
        print("You can still type a model id by hand - many gateways do not expose /models.")
        base_url = used_base

    model = choose_model(models) if models else None
    if not model:
        model = input(f"Model id [{current_model}]: ").strip() or current_model

    effort = values.get("AI_REASONING_EFFORT", "")
    effort_answer = input(f"Reasoning effort (Default/Low/Medium/High/Xhigh/Max) [{effort or 'Default'}]: ").strip()
    if effort_answer:
        effort = "" if effort_answer.lower() == "default" else effort_answer

    tokens = values.get("AI_MAX_TOKENS", "4096")
    tokens_answer = input(f"Max tokens [{tokens}]: ").strip()
    if tokens_answer.isdigit():
        tokens = tokens_answer

    print(f"\nTesting {model} at {base_url} ...")
    ok, detail = test_model(base_url, key, model)
    print(("  OK  " if ok else "  FAIL ") + detail)
    if not ok:
        if input("Save anyway? (y/n): ").strip().lower() not in ("y", "yes"):
            print("Nothing saved.")
            return None

    values.update({
        "AI_BASE_URL": base_url,
        "AI_API_KEY": key,
        "AI_MODEL": model,
        "AI_REASONING_EFFORT": effort,
        "AI_MAX_TOKENS": str(tokens),
    })
    save_env(env_path, values)
    print(f"\nSaved to {env_path} (the key is never printed).")
    print(f"Provider: {base_url}  model: {model}")
    return values


def show_check(env_path, providers):
    values = load_env(env_path)
    base = values.get("AI_BASE_URL", "(not set)")
    model = values.get("AI_MODEL", "(not set)")
    key = values.get("AI_API_KEY", "")
    print(f"Base URL : {base}")
    print(f"Model    : {model}")
    print(f"API key  : {mask(key)}")
    print(f"Reasoning: {values.get('AI_REASONING_EFFORT') or '(not sent)'}")
    print(f"Max tokens: {values.get('AI_MAX_TOKENS', '4096')}")
    if key:
        models, _, error = fetch_models(base, key)
        if models:
            print(f"Models   : {len(models)} available")
        else:
            print(f"Models   : could not list ({error})")
    return values


def main():
    ap = argparse.ArgumentParser(description="Configure any OpenAI-compatible AI provider.")
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--providers-file", default=DEFAULT_PROVIDERS)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--preset", default=None, help="provider id from providers.json")
    ap.add_argument("--presets", action="store_true", help="list curated providers and exit")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-test", action="store_true")
    args = ap.parse_args()

    providers = load_providers(args.providers_file)

    if args.presets:
        list_presets(args.providers_file)
        return 0

    if args.check:
        show_check(args.env_file, providers)
        return 0

    values = load_env(args.env_file)
    curated = find_provider(providers, args.preset) if args.preset else None
    if args.preset and not curated:
        print(f"Unknown preset '{args.preset}'. Run --presets to see the list.", file=sys.stderr)
        return 1

    if args.base_url or args.api_key or args.model or args.preset:
        base = (args.base_url or (curated["base_url"] if curated else None)
                or values.get("AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        key = args.api_key if args.api_key is not None else values.get("AI_API_KEY", "")
        model = args.model or values.get("AI_MODEL") or "gpt-4o-mini"

        if args.list_models:
            models, used_base, error = fetch_models(base, key)
            if not models:
                print(f"Could not list models ({error})", file=sys.stderr)
                return 1
            for model_id in models:
                print(model_id)
            return 0

        values.update({"AI_BASE_URL": base, "AI_API_KEY": key, "AI_MODEL": model})
        save_env(args.env_file, values)
        print(f"Saved {args.env_file}: {base} / {model}")
        if not args.no_test:
            ok, detail = test_model(base, key, model)
            print(("  OK   " if ok else "  FAIL ") + detail)
            if not ok:
                return 2
        return 0

    result = run_interactive(args.env_file, providers, preset=args.preset)
    return 0 if result else 1


if __name__ == "__main__":
    raise SystemExit(main())
