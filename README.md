POC: Mechanical crawl4ai crawler + embedded Ladybug graph storage + AI-synthesized document set (Python)

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
- `--graph-store <name>` (`ladybug` for a database on disk, `memory` for one that vanishes
  with the process - both are the same implementation, see `database/ladybug/store.py`)
- `--out`, `--max-pages`, `--page-concurrency`, `--headed`, `--fresh`/`--no-fresh`,
  `--config <path/to/other.yaml>`
- `--max-pages-per-run`, `--max-minutes-per-run`, `--full` - how much one run does before it
  stops and leaves the rest `Pending` for the next one, which resumes from exactly there.
  `--full` clears every budget and crawls until the frontier drains

Precedence for every setting: explicit CLI flag > `config/pragma.yaml` > environment variable (`.env`)
> built-in default.

Debugging a run: there are no file-based logs (`research_logs/`/`progress_logs/`/`graph_logs/`) -
the crawl's graph store *is* the live record. With `graph_store: ladybug` each site gets its own
database directory (`data/sites/<slug>.lbdb`); query it in Cypher over the node and relationship
tables `database/ladybug/schema.py` declares (`Page`, `Component`, `Interaction`, `Request`,
`NAVIGATES_TO`, ...), either through the `ladybug` package directly or through the store's own
`raw()` (guarded, reads only), `query(name, **params)` (the named-query library in
`database/ladybug/named_queries.py`) and `search_text()` (full-text) methods. With
`graph_store: memory` - the built-in default - inspect it in-process; nothing persists past one
run. `ARCHITECTURE.md` has the full schema, including which tables are written today and which
are staged but still empty.

No iteration/prompt-size tuning is needed anymore - there's no per-step LLM decision consuming a
token budget. There is also no per-page element cap: a page's interaction frontier is drained
exhaustively, since this project prioritizes a complete graph over a bounded worst-case runtime.
What bounds a crawl instead is pages and time - `--max-pages` caps the pages visited overall
(default: unbounded), while `--max-pages-per-run`/`--max-minutes-per-run` stop one run early and
hand the remainder to the next. Keep a minutes budget alongside a pages budget: a page whose DOM
keeps producing new components never finishes, so a page-only budget never trips.

Design: a micro-kernel `Engine` (`core/engine.py`) wires an `Agent` ("the brain"/LLM, `agents/`)
and a graph store ("the graph", `database/ladybug/`), both resolved by name from plugin registries
(`core/registry.py`), and drives them through three steps: `MechanicalCrawler`
(`spiders/orchestration/mechanical_loop/loop.py`, backed by `Crawl4AICrawler`, "the hands" -
crawl4ai-driven discovery and interaction) crawls the site and writes live to the graph store
(`GraphStoreSink`, `spiders/orchestration/graph_sink/sink.py`); two whole-site passes then group
components into families and project the navigation graph into modules and metrics
(`analysis/graph_projection.py`); finally `generators/pipeline.py` runs every configured document
generator over that graph - the AI-synthesized Digital Blueprint
(`generators/graph_prd_synthesizer.py`) is one of nine, not the run's single output. See
`ARCHITECTURE.md` for the full data flow. To add a new agent, subclass `Agent`
(`core/interfaces.py`), decorate it with `@AGENT_REGISTRY.register("name")` and import the module
from `core/bootstrap.py` so it registers itself at startup; a new document generator is the same
three steps against `DocumentGenerator` (`core/documents.py`) and `@DOCUMENT_REGISTRY`. A second
graph-store backend is a bigger job than it used to be: `GraphStore` is no longer an ABC, so
there is an interface to reintroduce before there is a plugin to write.

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
