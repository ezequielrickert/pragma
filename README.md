POC: Modular Scraper + Agent PRD Generator (Python)

Usage:
- Copy .env.example to .env and set URL and GEMINI_API_KEY (or OPENAI_API_KEY for OpenAI)
- To use Gemini: set AGENT_PROVIDER=gemini and optionally GEMINI_MODEL in .env
- pip install -r requirements.txt
- python3 -m playwright install
- python3 src/cli.py --url https://example.com

Optionally, copy `pragma.example.yaml` to `pragma.yaml` to declare your default wiring
(scraper/agent/generator plugin, output folders, headless mode, iteration limit) instead of
passing flags every time. `pragma.yaml` is auto-loaded from the repo root if present, or point
at another file with `--config path/to/file.yaml`. Any CLI flag you pass overrides the matching
YAML value; unset flags fall back to YAML, then to env vars, then to built-in defaults.

Swap plugins by name, no code changes required:
- `--scraper <name>` (default: `playwright`)
- `--agent <name>` / `--provider <name>` (default: `openai`; also `gemini`, `local`, `mock`)
- `--generator <name>` (default: `simple`, the Plan-Execute-Iterate "Ralph-Loop")

Design: a micro-kernel `Engine` (`src/core/engine.py`) orchestrates a `Scraper` ("the hands"),
an `Agent` ("the brain"/LLM), and a `PRDGenerator` orchestration strategy ("the loop"), all
resolved by name from plugin registries (`src/core/registry.py`). To add a new plugin, implement
the relevant interface in `src/core/interfaces.py`, decorate the class (or a builder function)
with `@SCRAPER_REGISTRY.register("name")` / `@AGENT_REGISTRY.register("name")` /
`@GENERATOR_REGISTRY.register("name")`, and import the module from `src/core/bootstrap.py` so it
registers itself at startup.

IMPORTANT: the way in which the agent understands the page is by running: "console.table($$('a'), ['innerHTML', 'href']);".
