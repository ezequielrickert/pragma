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
- `--out`, `--logs`, `--progress-logs`, `--graph-logs`, `--max-iterations`, `--wait-seconds`,
  `--batch-size`, `--headed`, `--unsafe`, `--storage-state <path>`, `--config <path/to/other.yaml>`

Precedence for every setting: explicit CLI flag > `pragma.yaml` > environment variable (`.env`)
> built-in default.

Crawling a site that requires login: `python3 src/cli.py login <url>` opens a visible browser,
lets you log in by hand, and saves the session to a file (default `storage_state.json`, gitignored
- it holds real cookies, never commit it). Pass that file on future runs with `--storage-state
<path>` (or `storage_state_path:` in `pragma.yaml`) so the crawl starts already authenticated -
entirely optional, every site that doesn't need login works exactly as before.

By default, Pragma runs in **safe mode**: a click/submit that looks like it would mutate real
state (a form submitting via POST, or a button like "Comprar"/"Eliminar"/"Confirmar") is detected
and *not* executed - it's recorded as a mutation boundary in the final report instead. Pass
`--unsafe` to disable this and let the model actually perform every action it chooses, including
real purchases/deletions/signups.

Debugging a run: `research_logs/` is the engine's live working-memory snapshot (overwritten each
stage, used to build the final PRD). `progress_logs/` is a separate, append-only trail of every
DISCOVERY/PLAN/ITERATION/SYNTHESIS stage in order, including the agent's raw response even when
it was malformed - open that file when a run stalls or an iteration seems to make no progress; it
also gets a rendered Mermaid diagram of the navigation graph appended once the run finishes.
`graph_logs/` has that same graph as JSON (a list of `{from, action, to}` edges) - which
component/action led from which page to which page - for feeding into other tooling.

Iteration prompts stay small regardless of site size: `batch_size` caps how many pending routes
and clickable elements are shown per iteration, and CLICK targets are referenced by a short number
from that list rather than a raw CSS path/class string (which on CSS-framework-heavy sites can be
hundreds of characters per element) - the biggest lever if a local model is timing out or taking a
long time per iteration. Lower `batch_size` and raise `--max-iterations` to compensate.

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

## Wiki

[`wiki/`](wiki/README.md) has durable, reusable domain knowledge extracted from building this
project - prompt engineering for multi-step agents, local-model constraints, Playwright automation
pitfalls, graph-based crawl tracking, and the debugging methodology used to find every bug in this
codebase. Read it before debugging a misbehaving agent loop, or when building the next one; it's
written to outlive this specific project and to seed Claude Code skills for future sessions.
