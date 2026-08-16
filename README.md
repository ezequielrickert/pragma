POC: Mechanical crawl4ai crawler + embedded DuckDB storage + AI-synthesized PRD generator (Python)

Setup:
- pip install -r requirements.txt
- python3 -m playwright install
- python3 cli.py config

`config` launches an interactive setup wizard (arrow-key menus, editable defaults, masked
API-key input) that persists your choice of agent/graph store, model names, and endpoints
to `config/pragma.yaml`, and any secrets (API keys) to `.env`. Run it once; re-run it any time to change
a setting - existing values are shown as defaults you can accept or overwrite, and it never
touches settings for providers you're not using.

Then just run an analysis with the URL as the only required input:
- `python3 cli.py https://example.com`
- or: `python3 cli.py` (prompts for the URL interactively if none was given)

Everything else - which agent/model, which graph store, output folder, headless mode, crawl
budget - comes from what you configured. Any of it can still be overridden per run with flags,
without touching your saved config:
- `--agent <name>` / `--provider <name>` (`local`, `mock`)
- `--graph-store <name>` (`memory`, `duckdb`)
- `--out`, `--element-budget`, `--max-pages`, `--headed`, `--fresh`/`--no-fresh`,
  `--config <path/to/other.yaml>`

Precedence for every setting: explicit CLI flag > `config/pragma.yaml` > environment variable (`.env`)
> built-in default.

Debugging a run: there are no more file-based logs (`research_logs/`/`progress_logs/`/
`graph_logs/`) - the crawl's graph store *is* the live record. With `graph_store: duckdb`, open the
database file directly with the `duckdb` CLI (or any DuckDB client) and query `site`-scoped tables
(`pages`, `components`, `edges`, ...) with plain SQL; with the default `graph_store: memory`,
inspect it in-process (nothing persists past one run).

No iteration/prompt-size tuning is needed anymore - there's no per-step LLM decision consuming a
token budget. `--element-budget` (default 200) is the only crawl-size knob: the per-page cap on
how many components `MechanicalCrawler` mechanically interacts with in one visit-pass, a backstop
against a pathological reveal-chain rather than a normal-case limit. `--max-pages` caps the total
number of pages visited (default: unbounded, crawl until the URL frontier is exhausted).

Design: a micro-kernel `Engine` (`core/engine.py`) wires an `Agent` ("the brain"/LLM,
`agents/`) and a `GraphStore` ("the graph", `database/`), both resolved by name from plugin
registries (`core/registry.py`), and drives them through two fixed steps: `MechanicalCrawler`
(`spiders/orchestration/mechanical_loop.py`, backed by `Crawl4AICrawler`, "the hands" - crawl4ai-driven
discovery and interaction) crawls the site and writes live to the graph store
(`GraphStoreSink`, `spiders/orchestration/graph_sink.py`); `GraphPRDSynthesizer`
(`generators/graph_prd_synthesizer.py`) then reads that graph back and produces the final
Markdown PRD. See `ARCHITECTURE.md` for the full data flow. To add a new agent or graph-store
plugin, implement the relevant interface in `core/interfaces.py`, decorate the class (or a
builder function) with `@AGENT_REGISTRY.register("name")` / `@GRAPH_STORE_REGISTRY.register("name")`,
and import the module from `core/bootstrap.py` so it registers itself at startup.

Provider config is encapsulated per agent, not piled into one growing `.env`: each agent module
(e.g. `agents/local_agent.py`) owns a small `Config` dataclass with a `from_env()`
classmethod that is the single source of truth for which env vars that provider needs. Non-secret
per-provider settings (model name, endpoint) can also be set in `config/pragma.yaml` under an `agents:`
block, keyed by provider name - only the block for the provider you're actually using is read.
Keep API keys and credential file paths in `.env`, never in a committed YAML file. Adding a new
provider (e.g. Anthropic) means adding one new agent module with its own `Config` + `from_env()`
and registering it - no changes anywhere else. The `config` wizard's provider-specific prompts
(`PROVIDER_FIELDS` in `core/wizard.py`) are the one place to extend when adding a provider's
interactive setup.

## Wiki

[`wiki/`](wiki/README.md) has durable, reusable domain knowledge extracted from building this
project - prompt engineering for multi-step agents, local-model constraints, browser automation
pitfalls (both Playwright-direct and crawl4ai-specific), graph-based crawl tracking, and the
debugging methodology used to find every bug in this codebase. Read it before debugging a
misbehaving agent/crawl loop, or when building the next one; it's written to outlive this specific
project and to seed Claude Code skills for future sessions.
