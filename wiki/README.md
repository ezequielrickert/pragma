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
| [crawl4ai-integration-pitfalls.md](crawl4ai-integration-pitfalls.md) | You're driving crawl4ai's `AsyncWebCrawler` via hooks/`js_code`/`session_id` for custom interaction (not just its built-in extraction pipeline), and a navigating click cascades into unrelated failures, or a result's URL doesn't match what actually happened. |
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
- "A click via crawl4ai js_code cascades into 'element not found' on every later action" → crawl4ai-integration-pitfalls
- "A crawl4ai result's URL doesn't match the page that actually loaded" → crawl4ai-integration-pitfalls (redirected_url, not .url)
- "Nothing to click after opening a dropdown/menu/combobox" → browser-automation-pitfalls (custom-widget ARIA roles)
- "Agent stuck in a loop revisiting the same page(s)" → graph-based-crawl-tracking, then debugging-agent-systems
- "Agent finishes/gives up before the page is actually done" → prompt-engineering (Principle 5/6), then graph-based-crawl-tracking
- "A fix had no effect on the live run" → tool-calling-and-execution-layers (stale standing-service process), then debugging-agent-systems
- "Most persisted nodes/records come out empty/blank even though interacted=true" → graph-based-crawl-tracking (ghost nodes from an auto-create fallback never getting the rich write)
- "A page's remaining components got silently dropped once a budget/cap was hit" → graph-based-crawl-tracking (bound work as internal rounds within one session, not requeue-via-re-navigation)
- "A revealed dropdown/menu's already-present-but-hidden options aren't detected as newly revealed" → browser-automation-pitfalls (visibility-transition diffing, not just DOM-presence diffing)
- "A whole run of 'element not found' failures on the same page, on components that definitely existed" → crawl4ai-integration-pitfalls (failure branch needs its own re-sync, not just the success branch's)
- "A crawl never terminates / keeps discovering 'new' pages forever on one site" → graph-based-crawl-tracking (session-token URLs need a coarser route-shape bound)
- "The same page seems to get re-scraped / re-fetched more than once, or a crawl of a redirecting site burns way more fetches than expected" → crawl4ai-integration-pitfalls (a follow-up-pass requeue must use the *resolved* URL, not the original request)
- "The same screen shows up as N separate near-duplicate pages in the output because its URL has a per-visit hash/token" → graph-based-crawl-tracking (route-shape as canonical storage identity, kept apart from literal-URL navigation identity)
- "A crawl is correctness-wise fine but way too slow at scale (hours for what should be minutes)" → graph-based-crawl-tracking (Queue.join()-based concurrent frontier, not just tuning fixed waits), then crawl4ai-integration-pitfalls (which fixed waits are actually tunable)
- "A button/interaction visibly changes the whole screen (a wizard step, an SPA route) but the crawler treats it as the same page, or merges it into the wrong page's component list" → graph-based-crawl-tracking (component-overlap-based state transitions - a same-URL DOM change can be a full replace, not just a reveal)
- "Trying to speed up/optimize a crawl4ai-driven fetch - which config flags actually help" → crawl4ai-integration-pitfalls (some flags don't touch the phase their name implies - read the source first)
- "A concurrent/multi-worker crawl visits, or writes a debug artifact for, the same page twice - a per-page file or browser session gets silently overwritten/raced" → graph-based-crawl-tracking (a dedup-bypassing re-queue path needs its own dequeue-time in-flight guard, not just the normal enqueue-time dedup set), then crawl4ai-integration-pitfalls (a debug snapshot must be keyed by session, not by resolved URL)
- "A crawl gets stuck on one page for a very long time / a single interaction keeps failing forever across resumes, even though nothing looks obviously broken" → crawl4ai-integration-pitfalls (a navigating click's failure path needs the same "did this move me to a different page" check the success path already has, plus content-identity memory of proven navigation triggers - not a retry-count cap)
- "A crawl is stuck retrying the same page for tens of minutes, every attempt failing identically (a Timeout or a 'Blocked by anti-bot protection' error), even though an earlier click genuinely, correctly navigated" → crawl4ai-integration-pitfalls (crawl4ai's own anti-bot heuristic can veto a navigation this project's own code had already correctly captured - trust the earlier, more specific signal; plus a consecutive-failure circuit breaker for when even the verification check is doomed)
- "A crawl gets stuck interacting with one same-page widget over and over - every attempt succeeds cleanly (no navigation, no error), it just never progresses" → graph-based-crawl-tracking (a same-page reveal chain needs the same churned-selector content-identity defense a cross-reload frontier already has)
- "A page's debug markdown snapshot loses a state it definitely showed earlier in the same run (e.g. a component's discovered items disappear once a later, unrelated interaction re-saves the file)" → graph-based-crawl-tracking (an artifact saved once per interaction, not once per page visit, needs an append-only companion file, not just an overwrite-only "live" one)
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
