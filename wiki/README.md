# Pragma Wiki: Building LLM-Driven Browser Agents

This is durable domain knowledge, not a changelog. `ARCHITECTURE.md` at the repo root documents
*what this project currently is*; this wiki documents *what we learned building it* — principles
and failure patterns general enough to apply to the next agent, the next scraper, or a completely
different project in this domain (autonomous LLM agents that drive tools like a browser).

Read `ARCHITECTURE.md` first if you want to know how Pragma works today. Read this wiki when
you're about to build or debug something in the same problem space: an LLM deciding actions that
a program executes against a stateful external system (a browser, an API, a filesystem), in a
loop, over many iterations, possibly with a small/local model.

## Index

| Doc | Read this when... |
|---|---|
| [prompt-engineering-for-llm-agents.md](prompt-engineering-for-llm-agents.md) | You're writing/debugging system prompts for a multi-step agent, especially one with several distinct call sites (plan vs. act vs. summarize). |
| [local-and-small-model-constraints.md](local-and-small-model-constraints.md) | Your agent works fine on GPT-4/Gemini but breaks, times out, hangs, or silently drops tool-call arguments on a local/small model. |
| [browser-automation-pitfalls.md](browser-automation-pitfalls.md) | You're driving Playwright (or similar) from generated selectors, and clicks/navigation silently fail, hit the wrong element, or a dropdown/combobox seems to have nothing in it. |
| [graph-based-crawl-tracking.md](graph-based-crawl-tracking.md) | Your agent loops, revisits the same state, needs to explain *how* it got from A to B, or a persistent store's history no longer matches reality. |
| [tool-calling-and-execution-layers.md](tool-calling-and-execution-layers.md) | You're designing or debugging how an agent's decisions turn into real actions — native function-calling vs. text fallback, a standing execution service, or where to draw the line between execution and reference-knowledge services. |
| [debugging-agent-systems.md](debugging-agent-systems.md) | An agent is "behaving badly" and you don't yet know if it's the model, the prompt, or the code. Read this first, before you start guessing. |

## Quick symptom → doc lookup

- "Model returns garbage / wrong format / ignores instructions" → prompt-engineering, then debugging-agent-systems
- "Model returns a huge/malformed plan instead of a short action" → prompt-engineering (shared-instruction conflict)
- "Local model times out / context length exceeded" → local-and-small-model-constraints
- "Model's tool call is missing a parameter the schema marks required" → local-and-small-model-constraints, then tool-calling-and-execution-layers
- "Model picks an invalid value for a constrained parameter" → local-and-small-model-constraints (structural enum, not prose)
- "Click does nothing / times out / hits the wrong element" → browser-automation-pitfalls
- "Nothing to click after opening a dropdown/menu/combobox" → browser-automation-pitfalls (custom-widget ARIA roles)
- "Agent stuck in a loop revisiting the same page(s)" → graph-based-crawl-tracking, then debugging-agent-systems
- "Agent finishes/gives up before the page is actually done" → prompt-engineering (Principle 5/6), then graph-based-crawl-tracking
- "A fix had no effect on the live run" → tool-calling-and-execution-layers (stale standing-service process), then debugging-agent-systems
- "Not sure where to even start" → debugging-agent-systems

## Turning this into skills

Each doc below is written close to skill-shape already: a trigger ("when you see X"), a mechanism
("why it happens"), and a concrete fix pattern. To turn one into a Claude Code skill:

1. Pick the doc closest to a recurring task (e.g. `debugging-agent-systems.md` for "diagnose a
   misbehaving agent loop").
2. Create `.claude/skills/<name>/SKILL.md` with frontmatter (`name`, `description` — the
   description is what triggers the skill, so make it symptom-shaped, e.g. "agent stuck in a
   loop, invalid actions, or timing out mid-run").
3. Body = the doc's "Fix pattern" / "Checklist" sections, trimmed to imperative steps.
4. Keep the wiki doc as the reference; the skill should point back here for the *why*, not
   duplicate it.

`debugging-agent-systems.md` and `graph-based-crawl-tracking.md` are the best first candidates —
they were used as an actual diagnostic checklist multiple times in one session.

## Where this came from

Every principle here was extracted from a real bug found while building Pragma's Ralph-Loop
(`SimplePRDGenerator` in `src/generators/prd_generator.py`) — an LLM agent that autonomously
crawls a website via Playwright. Nothing here is theoretical; each doc names the actual symptom
that was reported, the actual root cause, and the actual fix, then generalizes it. If you fix
something in this codebase that reveals a new instance of one of these patterns (or a genuinely
new pattern), add it here.
