---
name: wiki-context
description: Load relevant durable domain knowledge from wiki/ before debugging or building anything in the LLM-driven-browser-agent problem space (agent loops, revisits the same state, invalid/malformed model output, browser automation clicks/selectors failing, a dropdown or combobox with "nothing to click", local/small-model timeouts or dropped tool-call arguments, tool-calling or execution-layer design). Use this BEFORE proposing a fix or writing new agent/scraper/prompt code, not after - the wiki exists specifically to stop you from re-diagnosing a bug this project already found and fixed once.
---

# Wiki Context Loader

`wiki/` is this project's durable domain knowledge — principles and failure patterns general
enough to apply beyond this one codebase, distinct from `ARCHITECTURE.md` (which documents what
the system *currently is*). Read `wiki/README.md`'s own framing first if you haven't: it explains
the difference and why this exists.

## When this fires

Any time you're about to:
- Debug an agent/crawler/browser-automation system that's "behaving badly" and you don't yet know
  if it's the model, the prompt, or the code.
- Write or modify a system prompt / system_instruction for a multi-step agent loop.
- Generate CSS selectors or drive Playwright (or similar) from an LLM's decisions.
- Design or debug how an agent's decisions turn into real actions (native tool-calling, a text
  fallback, a standing execution service, MCP/REST/any transport).
- Track crawl/agent state across many steps (visited pages, loop detection, persistent stores).

## What to do

1. **Read `wiki/README.md` first** — its index table and "Quick symptom → doc lookup" section route
   a symptom description straight to the right doc(s). Don't guess which doc is relevant; match the
   actual symptom against that table.
2. **Read the matched doc(s) in full**, not just the section that looks closest — the "Symptom
   observed" framing means the right match isn't always the first thing that sounds similar, and a
   doc's later corrections/updates (search for "**Update —**") can reverse earlier guidance in the
   same file.
3. **Check `debugging-agent-systems.md`'s "Don't blame the model first" table** specifically before
   concluding a model/prompt is undersized or uncooperative — nearly every "the model is being
   dumb" symptom this project ever hit turned out to be a code or prompt bug instead.
4. **Apply the documented fix pattern**, don't just read for background — these are meant to be
   directly actionable (each one includes a concrete code pattern, not just a description of the
   problem).
5. **Cite the doc** when you explain the fix you made, so the reasoning trail back to the wiki stays
   visible (e.g. "per wiki/browser-automation-pitfalls.md's ARIA-role discovery gap...").

## What NOT to do

- Don't treat the wiki as optional background reading you can skip if you're confident — several of
  its entries exist specifically because a plausible-sounding "the model just isn't good enough"
  explanation delayed finding the real bug for an entire debugging session.
- Don't duplicate a wiki doc's content into a one-off explanation instead of reading and citing it —
  the wiki is the source of truth; summaries drift out of sync with it.
- Don't skip this because the current task "isn't really about agents" — if it touches prompts,
  selectors, tool-calling, or crawl/loop state in this codebase, it's in scope.

If you find yourself about to fix something and only afterward realize it matches a pattern already
documented here, that's a signal to load this skill earlier next time, not a failure — but do use
the `wiki-update` skill afterward if you found a genuinely new instance of a pattern, or a way an
existing doc's guidance was wrong or outdated.
