# Project Pragma: Architecture & Workflow

Pragma is an autonomous web-app archaeology tool. It follows a structured **Plan-Execute-Iterate** model (the "Ralph-Loop") to reverse-engineer complex frontend architectures.

## Core Phases

1.  **Phase 1: Discovery:** The agent navigates to the root URL to get an initial view of the layout and high-fidelity component DNA.
2.  **Phase 2: Planning:** The agent analyzes the initial discovery and generates an exhaustive research strategy.
3.  **Phase 3: Execution:** The agent enters an iterative loop where it:
    *   Reads the persistent research progress.
    *   Decides on deep-fidelity actions (`GOTO`, `CLICK` via text or CSS path).
    *   Updates the timestamped research log with detailed component findings.
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

## Directory Roles

- **`src/core/`**: The Kernel — `Engine`, plugin registries, shared interfaces/contracts
  (`PageState`, `Action`), and layered configuration (`PragmaConfig`).
- **`src/scrapers/`**: High-fidelity stateful Playwright session manager ("The Hands").
- **`src/agents/`**: LLM interface with Persona/Skill support ("The Brain").
- **`src/generators/`**: Manages the Plan-Execute-Iterate loop and persistent memory.
- **`src/utils/`**: Basic I/O operations.
- **`docs/`**: Final generated Digital Blueprint PRDs.
- **`research_logs/`**: Detailed, timestamped history of the agent's exploration and decisions.

---

## Persistent Memory & Documentation

Pragma maintains a detailed log in **`research_logs/`** for every session. This file captures:
*   The agent's initial research plan.
*   Every iteration's observations, including **Component DNA** (paths, roles, visibility).
*   Every action taken (`GOTO`, `CLICK`) and its outcome.

This ensures that the final PRD is a synthesis of the entire archaeological journey, and the logs provide a permanent audit trail of the agent's discovery process.
