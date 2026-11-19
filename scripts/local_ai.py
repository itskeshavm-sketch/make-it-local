"""Bring-your-own-key AI client - stdlib only, works with any OpenAI-compatible endpoint.

No pip install. No SDK. Reads AI_BASE_URL / AI_API_KEY / AI_MODEL from .env (or
the environment), and degrades gracefully when a provider rejects an optional
field:

    from local_ai import LocalAI, safe_complete

    ai = LocalAI()                       # reads .env
    if ai.configured:
        text = ai.complete("Summarise this: ...")
    else:
        text = offline_answer()

    # or let the fallback decide
    text = safe_complete(ai, "Summarise this: ...", fallback=offline_answer)

Supports OpenAI, OpenRouter, Groq, Together, DeepSeek, Mistral, xAI, Cerebras,
NVIDIA NIM, Ollama, LM Studio, vLLM, OpenCode Zen, or your own gateway.
Run `python setup_provider.py` to configure it interactively.
"""
import json
import os
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ENV = os.path.join(os.path.dirname(HERE), ".env")


def _read_env(path):
    from envfile import load_env
    return load_env(path)


class LocalAI:
    def __init__(self, base_url=None, api_key=None, model=None, env_file=DEFAULT_ENV,
                 max_tokens=4096, timeout=120, verbose=False):
        env = _read_env(env_file) if env_file and os.path.exists(env_file) else {}
        self.base_url = (base_url or env.get("AI_BASE_URL") or os.getenv("AI_BASE_URL") or "").rstrip("/")
        self.api_key = api_key or env.get("AI_API_KEY") or os.getenv("AI_API_KEY") or ""
        self.model = model or env.get("AI_MODEL") or os.getenv("AI_MODEL") or ""
        self.max_tokens = int(env.get("AI_MAX_TOKENS") or max_tokens)
        self.timeout = int(env.get("AI_TIMEOUT") or timeout)
        self.reasoning_effort = env.get("AI_REASONING_EFFORT") or os.getenv("AI_REASONING_EFFORT") or ""
        self.json_mode = str(env.get("AI_JSON_MODE") or os.getenv("AI_JSON_MODE") or "0").lower() in ("1", "true", "yes")
        self.verbose = verbose
        self.last_error = None

    # ------------------------------------------------------------- helpers
    @property
    def configured(self):
        # The key is optional: local servers (Ollama, LM Studio, vLLM) need none.
        # A cloud provider without a key answers 401, and safe_* fall back.
        return bool(self.base_url and self.model)

    def describe(self):
        if not self.configured:
            return "not configured (run setup_provider.py)"
        host = self.base_url.split("/v")[0].split("//")[-1]
        return f"{host}/{self.model}"

    def _post(self, path, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base_url + path,
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))

    def _build_payload(self, messages):
        payload = {"model": self.model, "messages": messages, "max_tokens": self.max_tokens}
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _create(self, messages):
        """One chat completion, dropping only the fields the provider refuses."""
        blocked = set()
        last_err = None
        for _ in range(6):
            payload = self._build_payload(messages)
            if "reasoning_effort" in blocked:
                payload.pop("reasoning_effort", None)
            if "response_format" in blocked:
                payload.pop("response_format", None)
            if "max_tokens" in blocked:
                payload.pop("max_tokens", None)
                payload["max_completion_tokens"] = self.max_tokens
            try:
                return self._post("/chat/completions", payload)
            except urllib.error.HTTPError as exc:
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")
                except Exception:
                    pass
                last_err = RuntimeError(f"HTTP {exc.code}: {body[:200]}")
                if exc.code in (401, 403):
                    break
                lowered = body.lower()
                if "max_token" in lowered:
                    blocked.add("max_tokens")
                elif "response_format" in lowered or "json_object" in lowered:
                    blocked.add("response_format")
                elif "reasoning" in lowered:
                    blocked.add("reasoning_effort")
                else:
                    break
            except Exception as exc:
                last_err = exc
                break
        raise last_err

    # ------------------------------------------------------------- API
    def chat(self, messages):
        """messages: [{'role':'user','content':'...'}] -> assistant text."""
        if not self.configured:
            raise RuntimeError("AI provider not configured. Run setup_provider.py")
        data = self._create(messages)
        return (data["choices"][0]["message"].get("content") or "").strip()

    def complete(self, prompt, system=None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def json(self, prompt, system=None, attempts=2):
        """Ask for JSON and parse it. Retries once with a stricter prompt."""
        extractor = ("Reply with a single JSON object and nothing else. "
                     "No markdown fences, no commentary.")
        for attempt in range(attempts):
            text = self.complete(prompt + ("\n" + extractor if attempt else ""), system=system)
            try:
                return parse_json(text)
            except ValueError as exc:
                self.last_error = exc
        raise ValueError(f"model did not return parsable JSON: {self.last_error}")


def parse_json(text):
    """Pull the first JSON object out of a model reply, fences and all."""
    if not text:
        raise ValueError("empty model reply")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(cleaned[start:end + 1])


def safe_complete(ai, prompt, fallback, system=None, verbose=False):
    """Try the AI; on any failure (offline, bad key, bad JSON) return fallback().

    This is the local-first contract: the AI is an enhancement, never a
    single point of failure.
    """
    if not ai.configured:
        if verbose:
            print("  ! no provider configured - using the offline path")
        return fallback()
    try:
        return ai.complete(prompt, system=system)
    except Exception as exc:
        ai.last_error = exc
        if verbose:
            print(f"  ! provider failed ({str(exc)[:140]}) - using the offline path")
        return fallback()


def safe_json(ai, prompt, fallback, system=None, verbose=False):
    """Same contract for structured output."""
    if not ai.configured:
        return fallback()
    try:
        return ai.json(prompt, system=system)
    except Exception as exc:
        ai.last_error = exc
        if verbose:
            print(f"  ! provider failed ({str(exc)[:140]}) - using the offline path")
        return fallback()


if __name__ == "__main__":
    ai = LocalAI()
    print("Provider:", ai.describe())
    if ai.configured:
        try:
            print("Ping:", ai.complete("ping"))
        except Exception as exc:
            print("Ping failed:", str(exc)[:200])
    else:
        print("Configure it with:  python setup_provider.py")
