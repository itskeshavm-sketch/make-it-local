# Project name

One-line description of what it does and who it is for.

## Status

| Piece | State | Notes |
|---|---|---|
| Core flow | **works** | tested on Windows 11, Python 3.12 |
| Offline fallback | **works** | AI unreachable -> deterministic answer |
| Linux / macOS | **works** | CI covers both |
| Live provider test | **works** | verified against OpenRouter + Groq |
| Packaging | not started | |
| Telemetry | none | no analytics, no phone-home |

> Rule: say what does not work. A status table beats a feature list.

## Quickstart

```powershell
irm https://raw.githubusercontent.com/OWNER/REPO/main/install.ps1 | iex
```

```bash
curl -fsSL https://raw.githubusercontent.com/OWNER/REPO/main/install.sh | bash
```

Then pick a provider and model (any OpenAI-compatible endpoint):

```
cd REPO
python scripts/setup_provider.py
```

## How it stays local-first

- **Bring your own key.** Nothing is shared, nothing is proxied.
- **Data stays on disk.** State is a JSON file you can read, edit and delete.
- **The AI is optional.** If the provider is down or the key is wrong, the app
  still answers using the offline path instead of failing.
- **Auditable.** No framework, no build step, no dependencies unless you add them.

## Layout

```
scripts/local_ai.py       BYOK client (any OpenAI-compatible endpoint)
scripts/ledger.py         atomic local JSON state
scripts/setup_provider.py provider wizard
scripts/envfile.py        tiny .env reader/writer
providers.json            curated OpenAI-compatible endpoints
```

## Configuration

`.env` (gitignored):

```
AI_BASE_URL=https://api.openai.com/v1
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
AI_REASONING_EFFORT=
AI_MAX_TOKENS=4096
```

See `providers.json` for ready-made base URLs, or run
`python scripts/setup_provider.py --presets`.

## License

MIT - copy it, change it, ship it.
