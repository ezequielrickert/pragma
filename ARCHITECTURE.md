# Project Pragma: Architecture & Workflow

Pragma is an autonomous web-app archaeology tool. It follows a structured **Plan-Execute-Iterate** model (the "Ralph-Loop") to reverse-engineer complex frontend architectures.

## Core Phases

1.  **Phase 1: Discovery:** The agent navigates to the root URL to get an initial view of the layout and high-fidelity component DNA.
2.  **Phase 2: Planning:** The agent analyzes the initial discovery and generates an exhaustive research strategy.
3.  **Phase 3: Execution:** The agent enters an iterative loop where it:
    *   Reads the persistent research progress.
    *   Decides on deep-fidelity actions (`GOTO <url>`, `CLICK <element number>` - CLICK refers to
        a numbered element from a short list shown that iteration, not a raw CSS path).
    *   Updates the timestamped research log with detailed component findings.
    *   Records a navigation-graph edge (which action led from which page to which page).
4.  **Phase 4: Synthesis:** The agent uses the entire research history to generate the final Digital Blueprint.

---

## The "Ralph-Loop" (Planned Autonomy)

```mermaid
sequenceDiagram
    participant CLI as cli.py
    participant Engine as core.Engine
    participant Gen as SimplePRDGenerator
    participant Log as research_logs/*.md
    participant Scraper as PlaywrightScraper
    participant Agent as LLM Agent (DOM-Digger)

    CLI->>Engine: Engine.from_config(config)
    Engine->>Gen: generate_prd(url)
    Gen->>Scraper: navigate(url)
    
    Gen->>Agent: Create Research Plan
    Agent-->>Gen: Plan
    Gen->>Log: Initialize Timestamped Log
    
    loop Research Loop (Max N Iterations)
        Gen->>Log: Read Progress
        Gen->>Agent: Next Action?
        Agent-->>Gen: GOTO/CLICK
        Gen->>Scraper: Execute Action
        Scraper-->>Gen: High-Fidelity State
        Gen->>Log: Update Progress with Component DNA
    end
    
    Gen->>Agent: Synthesize Final Map from Progress
    Agent-->>Gen: Final PRD
    Gen-->>Engine: Final PRD text
    Engine-->>CLI: Save PRD to docs/
    Gen->>Scraper: close()
```

---

## Micro-kernel: Plugins & Registries

Pragma's kernel is `src/core/engine.py::Engine`. It knows nothing about Playwright, Gemini, or
the specifics of the Ralph-Loop — it only knows how to resolve named plugins from three
registries (`src/core/registry.py`) and wire them together:

- **`SCRAPER_REGISTRY`**: implementations of the `Scraper` interface ("The Hands") — currently
  `playwright`.
- **`AGENT_REGISTRY`**: implementations of the `Agent` interface ("The Brain"/LLM backend) —
  currently `gemini`, `openai`, `local`, `mock`.
- **`GENERATOR_REGISTRY`**: implementations of the `PRDGenerator` interface (the orchestration
  strategy/loop) — currently `simple` (the Ralph-Loop described above).

Each plugin module self-registers via a decorator (`@SCRAPER_REGISTRY.register("playwright")` on
`PlaywrightScraper`, etc.). `src/core/bootstrap.py` imports every plugin module once so their
registrations run before the CLI resolves names from config. Adding a new scraper, agent, or
orchestration strategy never requires touching the Engine — only implementing the interface,
registering it, and adding one import line to `bootstrap.py`.

Configuration (`src/core/config.py::PragmaConfig`) declares *which* plugins to wire and basic
pipeline settings (output/log dirs, headless, iteration count). It merges, in increasing
precedence: built-in defaults, environment variables, an optional `pragma.yaml` file, and
explicit CLI flags — so a checked-in `pragma.yaml` can set project-wide defaults while any run
can override a single value from the command line.

The `Scraper` <-> `PRDGenerator` contract is a `PageState` dataclass (`url, title, metadata,
components, links`) rather than a raw dict, and the agent's `GOTO`/`CLICK`/`FINISH` decisions are
parsed via `parse_action()` into an `Action` dataclass — both defined in
`src/core/interfaces.py`. This means a new scraper only needs to produce a `PageState`, and a new
orchestration strategy only needs to consume one, without either side depending on the other's
internal shape.

---

## Keeping Iteration Prompts Small: Indexed CLICK Targets

`_build_iteration_prompt` (`src/generators/prd_generator.py`) caps pending routes and DNA
components at `batch_size` items each - but item *count* isn't the only driver of prompt size.
Each DOM component's full CSS path (`body > header > ... > nav > ... > a`) and `attributes.class`
(often hundreds of characters on CSS-framework-heavy sites) used to be dumped verbatim as JSON for
every shown component, regardless of `batch_size`. On a page with a deep/complex nav, that alone
could dwarf the count-based cap and drive iteration/inference time up independent of `batch_size`.

DNA is now rendered as a short numbered list (`[1] <a> 'About'`) — tag and text only. The model
refers to a CLICK target by its number (`CLICK 3`); `_resolve_click_selector` maps that back to the
real CSS path via `_dna_index_map`, which is rebuilt fresh every iteration and never shown to the
model. This is the single largest per-iteration prompt-size reduction available, on top of
`batch_size`, `wait_seconds`, and provider `timeout` for taming slow/small local models. For
resilience across model tiers, a CLICK target that isn't a valid number still falls back to being
treated as a literal CSS path (if it looks like one) or matched by visible text.

---

## Navigation Graph

Route status (pending/visited) doesn't capture *how* the crawl got from one page to another. Each
successful GOTO/CLICK is recorded as a `{from, action, to}` edge in `self.graph_edges`
(`_handle_iteration_result`), written at the end of the run as JSON to `graph_log_file` and
rendered as a Mermaid flowchart appended to `progress_log_file` (`_write_graph_log`,
`_build_mermaid_graph`) — so the exploration path is visible both to tooling (JSON) and to a human
glancing at the debug trail (auto-rendered diagram in GitHub/VS Code markdown preview).

---

## Per-Provider Config Encapsulation

As more AI providers get added, their env vars, credentials, and model settings must not pile
up into one flat, ever-growing `.env`. Each agent module owns a small `Config` dataclass
colocated with its implementation, with a `from_env()` classmethod that is the *only* place that
reads that provider's env vars:

- `GeminiConfig` (`src/agents/gemini_agent.py`): `GEMINI_API_KEY`, `GEMINI_MODEL`.
- `GeminiOAuthConfig` (`src/agents/gemini_oauth_agent.py`): `GOOGLE_APPLICATION_CREDENTIALS`,
  `GEMINI_MODEL`.
- `OpenAIConfig` (`src/agents/openai_agent.py`): `OPENAI_API_KEY`, `OPENAI_MODEL`.
- `LocalConfig` (`src/agents/local_agent.py`): `LOCAL_API_URL`, `LOCAL_MODEL`.

`src/agents/providers.py` (the `gemini`/`openai` registry builders) only decides *which* class to
instantiate and applies optional overrides on top of each `Config.from_env()` — it never reads a
provider's env vars itself. Those overrides come from `PragmaConfig.agents`, an optional nested
`agents:` block in `pragma.yaml` keyed by provider name (see `pragma.example.yaml`), letting
non-secret settings (model name, base URL) live in version-controllable config scoped per
provider instead of more prefixed globals in `.env`. Secrets (API keys, credential paths) stay in
`.env` only.

`python3 src/cli.py config` (`src/core/wizard.py`) is the interactive front door to all of this:
an arrow-key menu (via `questionary`, with a plain-`input()` fallback when there's no TTY) walks
through scraper/agent/generator selection and that provider's `PROVIDER_FIELDS`, then writes
non-secret answers to `pragma.yaml` and secret answers to `.env` via `upsert_env_vars()`
(`src/utils/io.py`), which patches just the changed keys in place. Existing values are shown as
editable defaults, so re-running the wizard to tweak one setting never clobbers the rest.

Consequences: switching `--agent` never requires knowing another provider's variables, and
adding a new provider (e.g. Anthropic) is: write `anthropic_agent.py` with its own `Agent`
subclass + `AnthropicConfig.from_env()`, register a builder in `providers.py` (or decorate the
class directly if it needs no OAuth-vs-REST branching), and add one import to
`src/core/bootstrap.py`. No other file changes.

---

## Directory Roles

- **`src/core/`**: The Kernel — `Engine`, plugin registries, shared interfaces/contracts
  (`PageState`, `Action`), and layered configuration (`PragmaConfig`).
- **`src/scrapers/`**: High-fidelity stateful Playwright session manager ("The Hands").
- **`src/agents/`**: LLM interface with Persona/Skill support ("The Brain").
- **`src/generators/`**: Manages the Plan-Execute-Iterate loop and persistent memory.
- **`src/utils/`**: Basic I/O operations.
- **`docs/`**: Final generated Digital Blueprint PRDs.
- **`research_logs/`**: Live status snapshot (route table) for the current session, overwritten on
  every update. This is the file `_synthesize_tree_report` reads back in to build the final PRD.
- **`progress_logs/`**: Append-only debug trail, one entry per DISCOVERY/PLAN/ITERATION/SYNTHESIS
  stage, in order, for the entire run. Never overwritten, never read back by the engine itself -
  purely for a human to inspect what the agent actually said/did, e.g. to spot a malformed
  response or a bad prompt. Location configurable via `progress_logs_dir` in `pragma.yaml` or
  `--progress-logs`. Gets a rendered Mermaid flowchart of the navigation graph appended once the
  run finishes.
- **`graph_logs/`**: The navigation graph as JSON - a list of `{from, action, to}` edges, one per
  successful GOTO/CLICK, recording which action led from which page to which page. Configurable
  via `graph_logs_dir` / `--graph-logs`.

---

## Persistent Memory & Debugging

Pragma keeps two separate logs per session, serving different purposes:

- **`research_logs/{slug}_research_{ts}.md`**: the engine's *working memory*. `_update_progress()`
  rewrites this file on every stage with the current route table and the latest log entry only -
  it's a snapshot, not a history. This is what gets fed back into the agent for the final
  synthesis step (`_synthesize_tree_report`), so it only needs to reflect current state.
- **`progress_logs/{slug}_progress_{ts}.md`**: the *audit trail*. Every DISCOVERY/PLAN
  CREATED/ITERATION N/SYNTHESIS stage is appended here in full, including the agent's raw
  response text even when it was malformed or failed to produce an action. This is the file to
  open when debugging why a run stalled, an iteration produced no progress, or a model's output
  didn't match the expected `GOTO`/`CLICK`/`FINISH` format.
