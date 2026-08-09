# Tool-Calling and Execution Layers

Applies whenever an LLM's decisions need to actually *do* something in the outside world — click a
button, call an API, run a query — regardless of whether that's wired up via native OpenAI-style
function-calling, a hand-rolled JSON-in-text protocol, or a formal protocol like MCP.

## The model never calls anything directly — the orchestrator always mediates

Easy to lose sight of once a system has several layers: whatever chat-completions endpoint you're
calling, the model's only output is text (plain, or a `tool_calls` JSON blob if the server/model
supports it). It has no network access and cannot dial an API, hit an endpoint, or run code itself.
Every "tool call" is the calling program parsing that text and deciding what to actually execute.

**Why this matters in practice**: it means the *transport* between your orchestrator and whatever
executes actions (a direct in-process call, a REST API, an MCP server) is invisible to the model
and irrelevant to its own reliability. Moving from one to another (this project moved from MCP to a
plain REST API, then folded the REST API's execution and reference-docs endpoints into one process)
changed zero lines of what the model was ever shown — the entire migration was an orchestrator-side
concern. Don't expect a transport change to fix a model-output-reliability problem; it can't, by
construction. See [local-and-small-model-constraints.md](local-and-small-model-constraints.md) for
what actually does affect that.

## Native tool-calling degrades — build the fallback ladder before you need it

**Symptom observed**: a local OpenAI-compatible server accepted the `tools` request parameter
without error, but the model's own chat template silently ignored it and replied with plain text
instead of a `tool_calls` object — no error, just a response shaped like the *other* path.

**Fix pattern**: probe for native support once, cache the result, and fall back gracefully rather
than assuming any one calling convention:

```python
def act(self, prompt, tools, system_instruction=None):
    if self._tools_supported is not False:
        action = self._try_native_tool_call(prompt, tools, system_instruction)
        if action is not None:
            self._tools_supported = True
            return action
        self._tools_supported = False
    return self._text_fallback(prompt, tools, system_instruction)  # JSON-in-text, then legacy grammar
```

Cache the outcome per agent instance so a server/model that doesn't support native calling only
costs one failed round trip for the whole run, not one per iteration. Keep a final plain-text
grammar fallback beneath the JSON-in-text one too — a three-tier ladder (native → JSON-in-text →
legacy verb grammar) degrades gracefully instead of hard-failing the first time a model doesn't
cooperate with the top tier.

## A standing execution service is easy to leave running with stale code

**Symptom observed**: a fix to a DOM-discovery function had zero effect on a live run — twice — with
no error, no exception, nothing to indicate anything was wrong. The execution server backing that
run had been started *before* the fix and was still running, holding the old code in memory; Python
processes don't hot-reload a module just because the file on disk changed underneath them.

**Fix pattern**: if a component is meant to be a long-running, standing service (persistent browser
session, warm state across many runs) rather than spawned fresh per invocation, that persistence
benefit comes with a real cost during active development — a restart is required after every code
change, and nothing will tell you if you forget. Two mitigations, not a full fix for either:

- A dev-mode auto-reload flag (`uvicorn --reload` or equivalent) for when you're actively editing
  the service's own code, explicitly opt-in and off by default (a reload drops in-memory state —
  a live browser session — which defeats the point of the standing-service model otherwise).
- Check for a stale process (`ps aux | grep <service>`) as a standard first move whenever "I just
  fixed this and it's still broken" — before spending time re-diagnosing a bug that's already fixed
  on disk, confirm the running process actually has the fix loaded.

## Where to draw the line between "execution" and "reference knowledge" services

If you split responsibilities across services (one that executes real actions, one that serves
reference/help content), keep the split along a clear axis: does this data live in per-run
orchestrator state (ref numbering, what's been interacted with, current page), or is it static and
shared across every run (how a UI pattern works, what a parameter means)? The former belongs with
whatever owns the run's state — round-tripping it through a separate service that doesn't otherwise
participate in that state just to hand it back adds indirection with no benefit. The latter is a
legitimate candidate for a separate, stateless service any number of runs can share. See
[prompt-engineering-for-llm-agents.md](prompt-engineering-for-llm-agents.md)'s Principle 6 for the
related point about *how* each kind should reach the model (deterministic injection vs. optional
on-demand lookup) — that's a model-facing design question layered on top of this
service-boundary one.
