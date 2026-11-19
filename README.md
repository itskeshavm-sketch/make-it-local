# make-it-local

**Turn any AI app into a local-first, bring-your-own-key app — in one command.**

No subscription, no shared API keys, no data leaving the machine, and no single
point of failure: if the AI is down, the app still answers with the offline path.

Built on the same pattern as [hush](https://github.com/itskeshavm-sketch/hush),
[VyaparTrack](https://github.com/itskeshavm-sketch/vyapartrack),
[Recorda](https://github.com/itskeshavm-sketch/recorda) and
[ai-trading-bots](https://github.com/itskeshavm-sketch/ai-trading-bots).

## Status

| Piece | State | Notes |
|---|---|---|
| Provider wizard | **works** | 15 providers curated, live model list, verified ping |
| BYOK client | **works** | any OpenAI-compatible endpoint, stdlib only |
| Provider fallbacks | **works** | drops only the field the provider rejects |
| Offline fallback | **works** | AI down -> deterministic answer, never a crash |
| Local ledger | **works** | atomic writes, survives a kill mid-write |
| Windows / macOS / Linux | **works** | CI covers all three |
| Dependencies | **zero** | nothing to `pip install` for the toolkit itself |
| Telemetry | none | no analytics, no phone-home |

## Quickstart

**PowerShell (Windows):**
```powershell
irm https://raw.githubusercontent.com/itskeshavm-sketch/make-it-local/main/install.ps1 | iex
```

**Bash (macOS / Linux / WSL / Git Bash):**
```bash
curl -fsSL https://raw.githubusercontent.com/itskeshavm-sketch/make-it-local/main/install.sh | bash
```

Then pick a provider and a model — the wizard fetches that provider's live model
list, so you choose from what actually exists:

```
cd make-it-local
python scripts/setup_provider.py

Base URL [https://api.openai.com/v1]: https://api.groq.com/openai/v1
API key (hidden):
Fetching model list from https://api.groq.com/openai/v1/models ...
OK - 62 model(s) available.
Filter by text (Enter = show all): llama
  [  1] llama-3.3-70b-versatile
  [  2] llama-3.1-8b-instant
Pick a model (number, or type the model id): 1
Testing llama-3.3-70b-versatile ...
  OK   model answered: 'pong'

Saved to .env (the key is never printed).
```

Or skip the wizard:
```
python scripts/setup_provider.py --preset groq --api-key gsk_... --model llama-3.3-70b-versatile
python scripts/setup_provider.py --presets      # list curated providers
python scripts/setup_provider.py --check        # what is configured right now
```

## Use it

```python
import sys; sys.path.insert(0, "scripts")
from local_ai import LocalAI, safe_complete, safe_json
from ledger import Ledger

ai = LocalAI()                      # reads .env

# 1. plain text, with an offline fallback
answer = safe_complete(ai, "Summarise this: ...", fallback=lambda: "offline answer", verbose=True)

# 2. structured output, same contract
data = safe_json(ai, "Return JSON {city, monsoon}", fallback=offline_answer)

# 3. local state that cannot be corrupted
db = Ledger("state.json", default={"runs": []})
db.append("runs", {"answer": answer})
```

Copy the four files in `scripts/` into your project — that is the whole toolkit.

## The four pieces

| File | What it does |
|---|---|
| `scripts/setup_provider.py` | wizard: base URL + hidden key + live model list -> `.env`, then verifies the model answers |
| `scripts/local_ai.py` | BYOK client for any OpenAI-compatible endpoint, with `safe_complete` / `safe_json` fallbacks |
| `scripts/ledger.py` | atomic local JSON state (`tmp` + `os.replace`, survives a crash mid-write) |
| `scripts/envfile.py` | tiny `.env` reader/writer that preserves comments and other keys |
| `providers.json` | curated endpoints + free models — **contributions welcome** |
| `templates/README.status.md` | the status-table README convention |

## Why not the `openai` package?

The client uses `urllib` from the standard library. That means:

- **zero install** — the toolkit works before anything is set up
- **small enough to audit** — ~200 lines you can read in one sitting
- **no version churn** — an SDK upgrade can never break your app

If you would rather use the SDK, `local_ai.py` is a single file — swap
`_post()` for `client.chat.completions.create()` and keep everything else.

## Providers

`providers.json` carries the curated list. Highlights:

| Provider | Base URL | Key | Notes |
|---|---|---|---|
| OpenAI | `https://api.openai.com/v1` | yes | `gpt-4o-mini` is the cheap default |
| OpenRouter | `https://openrouter.ai/api/v1` | yes | 200+ models, many with a `:free` variant |
| Groq | `https://api.groq.com/openai/v1` | yes | very fast, rate-limited free tier |
| DeepSeek | `https://api.deepseek.com/v1` | yes | very cheap, strong reasoning |
| Mistral | `https://api.mistral.ai/v1` | yes | |
| NVIDIA NIM | `https://integrate.api.nvidia.com/v1` | yes | huge open-model catalogue, free tier |
| Gemini (compat) | `https://generativelanguage.googleapis.com/v1beta/openai` | yes | `gemini-2.0-flash` free tier |
| Ollama | `http://localhost:11434/v1` | **no** | runs on your machine |
| LM Studio | `http://localhost:1234/v1` | **no** | runs on your machine |
| vLLM | `http://localhost:8000/v1` | **no** | point at your own server |

Add one: `python scripts/setup_provider.py --presets`, then open a PR against
`providers.json`. Entries with `"verified": true` were checked against the live
`/models` endpoint.

## How the fallbacks work

Real providers reject optional fields. The client remembers every rejection and
drops only that field on the next attempt — no repeated broken combinations:

| Provider says | Client does |
|---|---|
| `unsupported parameter: max_tokens` | retries with `max_completion_tokens` |
| `response_format is not supported` | retries without JSON mode |
| `unknown parameter: reasoning` | retries without the reasoning field |
| `401 / 403` | stops immediately, reports the auth problem |
| network down / timeout | raises, so your `fallback()` takes over |

## Used by

The same pattern powers these projects:

- [hush](https://github.com/itskeshavm-sketch/hush) — E2E encrypted messaging
- [VyaparTrack](https://github.com/itskeshavm-sketch/vyapartrack) — WhatsApp shop ledger
- [Recorda](https://github.com/itskeshavm-sketch/recorda) — meeting notes, no bot in the call
- [ai-trading-bots](https://github.com/itskeshavm-sketch/ai-trading-bots) — paper trading on NSE + crypto

## Contributing

The highest-value contribution is `providers.json`: a new endpoint, a corrected
base URL, a free model that actually still works. Add an entry, mark it
`"verified": true` only if you checked it, and open a PR.

## License

MIT — copy it, change it, ship it.
