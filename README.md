POC: Modular Scraper + Agent PRD Generator (Python)

Setup:
- pip install -r requirements.txt
- python3 -m playwright install
- python3 src/cli.py config

`config` launches an interactive setup wizard (arrow-key menus, editable defaults, masked
API-key input) that persists your choice of scraper/agent/generator, model names, and endpoints
to `pragma.yaml`, and any secrets (API keys) to `.env`. Run it once; re-run it any time to change
a setting - existing values are shown as defaults you can accept or overwrite, and it never
touches settings for providers you're not using.

Then just run an analysis with the URL as the only required input:
- `python3 src/cli.py https://example.com`
- or: `python3 src/cli.py` (prompts for the URL interactively if none was given)

Everything else - which scraper, which agent/model, output folders, headless mode, iteration
limit - comes from what you configured. Any of it can still be overridden per run with flags,
without touching your saved config:
- `--scraper <name>` (default: `playwright`)
- `--agent <name>` / `--provider <name>` (also `gemini`, `openai`, `local`, `mock`)
- `--generator <name>` (default: `simple`, the Plan-Execute-Iterate "Ralph-Loop")
- `--out`, `--logs`, `--max-iterations`, `--headed`, `--config <path/to/other.yaml>`

Precedence for every setting: explicit CLI flag > `pragma.yaml` > environment variable (`.env`)
> built-in default.

Design: a micro-kernel `Engine` (`src/core/engine.py`) orchestrates a `Scraper` ("the hands"),
an `Agent` ("the brain"/LLM), and a `PRDGenerator` orchestration strategy ("the loop"), all
resolved by name from plugin registries (`src/core/registry.py`). To add a new plugin, implement
the relevant interface in `src/core/interfaces.py`, decorate the class (or a builder function)
with `@SCRAPER_REGISTRY.register("name")` / `@AGENT_REGISTRY.register("name")` /
`@GENERATOR_REGISTRY.register("name")`, and import the module from `src/core/bootstrap.py` so it
registers itself at startup.

Provider config is encapsulated per agent, not piled into one growing `.env`: each agent module
(e.g. `src/agents/gemini_agent.py`) owns a small `Config` dataclass with a `from_env()`
classmethod that is the single source of truth for which env vars that provider needs. Nobody
else reads `GEMINI_API_KEY`, `OPENAI_MODEL`, etc. directly. Non-secret per-provider settings
(model name, endpoint) can also be set in `pragma.yaml` under an `agents:` block, keyed by
provider name - only the block for the provider you're actually using is read, so switching to
`--agent mock` or `--agent local` never requires you to look at Gemini/OpenAI settings at all.
Keep API keys and credential file paths in `.env`, never in a committed YAML file. Adding a new
provider (e.g. Anthropic) means adding one new agent module with its own `Config` + `from_env()`
and registering it - no changes anywhere else. The `config` wizard's provider-specific prompts
(`PROVIDER_FIELDS` in `src/core/wizard.py`) are the one place to extend when adding a provider's
interactive setup.

IMPORTANT: the way in which the agent understands the page is by running: "console.table($$('a'), ['innerHTML', 'href']);".
