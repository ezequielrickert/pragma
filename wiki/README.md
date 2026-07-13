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
| [local-and-small-model-constraints.md](local-and-small-model-constraints.md) | Your agent works fine on GPT-4/Gemini but breaks, times out, or hangs on a local/small model. |
| [browser-automation-pitfalls.md](browser-automation-pitfalls.md) | You're driving Playwright (or similar) from generated selectors, and clicks/navigation silently fail or hit the wrong element. |
| [graph-based-crawl-tracking.md](graph-based-crawl-tracking.md) | Your agent loops, revisits the same state, or you need to explain *how* it got from A to B. |
| [debugging-agent-systems.md](debugging-agent-systems.md) | An agent is "behaving badly" and you don't yet know if it's the model, the prompt, or the code. Read this first, before you start guessing. |

## Quick symptom → doc lookup

- "Model returns garbage / wrong format / ignores instructions" → prompt-engineering, then debugging-agent-systems
- "Model returns a huge/malformed plan instead of a short action" → prompt-engineering (shared-instruction conflict)
- "Local model times out / context length exceeded" → local-and-small-model-constraints
- "Click does nothing / times out / hits the wrong element" → browser-automation-pitfalls
- "Agent stuck in a loop revisiting the same page(s)" → graph-based-crawl-tracking, then debugging-agent-systems
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
