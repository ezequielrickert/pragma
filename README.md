# Pragma - Web Page to PRD Generator

Pragma is a small, modular Python project that:

1. Scrapes a web page with Playwright.
2. Extracts HTML + links.
3. Sends that context to an LLM agent.
4. Writes a markdown PRD file into `docs/`.

It is built as a POC, but with clear interfaces so components are easy to swap.

## What it does

- Scrapes rendered page content (`html`) and discovered links (`links`).
- Generates a concise PRD in markdown with sections like goals, users, features, and acceptance criteria.
- Supports multiple agent providers:
  - Gemini via API key (`GeminiAgent`)
  - Gemini via service account OAuth (`GeminiOAuthAgent`)
  - OpenAI chat completion (`OpenAIAgent`)
- Falls back to a local mock agent when provider setup fails.

## Project structure

```text
src/
  interfaces.py              # Scraper, Agent, PRDGenerator abstractions
  cli.py                     # Main CLI entrypoint
  run_sample.py              # Simple sample runner + MockAgent
  scrapers/
	playwright_scraper.py    # Playwright-based scraper
  agents/
	openai_agent.py          # OpenAI implementation
	gemini_agent.py          # Gemini API key implementation
	gemini_oauth_agent.py    # Gemini service-account OAuth implementation
  generators/
	prd_generator.py         # Prompt builder + PRD generation pipeline
docs/                        # Generated PRD outputs
tests/
  test_imports.py            # Basic import smoke test
```

## Quick start

### 1) Install dependencies

```powershell
pip install -r requirements.txt
python -m playwright install
```

### 2) Configure environment

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and set at least:

- `URL` (optional if always passing `--url`)
- `AGENT_PROVIDER` (`gemini` or `openai`)
- matching credentials (`GEMINI_API_KEY` or `OPENAI_API_KEY`)

### 3) Run

```powershell
python src/cli.py --url https://example.com
```

Output file is written to `docs/` with a timestamped name like:

`example.com_prd_20260513T120000Z.md`

## Configuration

Use `.env` (loaded automatically by `python-dotenv`).

### Core variables

- `URL` - default URL if `--url` is not provided.
- `AGENT_PROVIDER` - `gemini` (default recommendation) or `openai`.
- `OPENAI_MODEL` - defaults to `gpt-3.5-turbo`.

### Gemini (API key)

- `GEMINI_API_KEY`
- `GEMINI_MODEL` (example: `models/gemini-1.5-flash`)

### Gemini (OAuth service account)

- `GOOGLE_APPLICATION_CREDENTIALS` - path to service account JSON.
- `GEMINI_MODEL` - model path used by OAuth agent.

When `AGENT_PROVIDER=gemini`, the CLI prefers OAuth if `GOOGLE_APPLICATION_CREDENTIALS` is present; otherwise it uses API key mode.

### OpenAI

- `OPENAI_API_KEY`
- optional `OPENAI_MODEL`

## CLI usage

```powershell
python src/cli.py --url <target-url> --out docs
```

Arguments:

- `--url`, `-u` - URL to scrape (falls back to `URL` env var).
- `--out`, `-o` - output directory (default: `docs`).

## Testing

Run the current smoke test suite:

```powershell
python -m pytest -q
```

## Troubleshooting

- `URL must be provided...`
  - pass `--url` or set `URL` in `.env`.
- Gemini `404` errors
  - verify API key is tied to a project with Generative Language API enabled.
  - verify selected `GEMINI_MODEL` is available to your account/key.
- Gemini `403` / permission errors
  - check key restrictions and API access; or use OAuth service account flow.
- OpenAI initialization failures
  - verify `OPENAI_API_KEY` and package version compatibility.

## Design notes

The project follows three explicit interfaces in `src/interfaces.py`:

- `Scraper`: produces normalized scraped data.
- `Agent`: turns a prompt into generated text.
- `PRDGenerator`: composes final PRD markdown from scraped data.

Because components depend on interfaces, you can replace scraper, model provider, or generator logic with minimal changes.
