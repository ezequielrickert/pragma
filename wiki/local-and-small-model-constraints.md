# Local and Small-Model Constraints

Applies whenever your agent loop needs to work against both cloud models (large context, fast
inference, tolerant of verbose prompts) and local/small models (small context, slow inference on
CPU/modest hardware, easily confused by long or repetitive text). Design for the weaker end; the
stronger end will always cope.

## Context window overflow

**Symptom observed**: `Local API Error (400): the number of tokens to keep from the initial
prompt is greater than the context length (n_keep: 35743 >= n_ctx: 4096)`.

**Cause**: the prompt sender was including the *entire* discovered page/route dataset every
iteration, with no cap. Fine for a cloud model with a 128k+ context window; fatal for a local model
serving a 4k window.

**Fix pattern**: cap what goes into every prompt, always, regardless of provider — never assume
the deployed model has room for "everything." See `batch_size` in `_build_iteration_prompt`
(`src/generators/prd_generator.py`) — it slices both the pending-routes list and the DNA/component
list to a fixed count every iteration, no matter how large the underlying site is.

## Item *count* isn't the only thing that blows up a prompt — item *verbosity* matters just as much

**Symptom observed**: even after capping item count to 20, iterations on a real, CSS-framework-
heavy site still took 600+ seconds and timed out. The cause wasn't count — each of those 20 "DNA"
items included a full CSS path (sometimes 150+ characters, deeply nested) and an `attributes.class`
string (hundreds of characters on utility-class-heavy frameworks like Tailwind). 20 verbose items
can dwarf what looks like a "capped" prompt.

**Fix pattern**: audit not just "how many items" but "how many characters per item" you're
sending. Strip anything the model doesn't need to make its decision — it needs enough to
*identify* an option (a short label, a tag name), not everything needed to *execute* it (a full
selector). Keep the execution-only data (the real CSS path) in an internal, per-iteration lookup
table the program uses after the model picks by index — never in the prompt itself. This is the
same principle as [Principle 4 in prompt-engineering-for-llm-agents.md](prompt-engineering-for-llm-agents.md),
stated from the size-budget angle instead of the reliability angle — they're the same fix.

## Inference latency scales with prompt size, especially on CPU-bound local models

For a cloud model, sending more context per call is often *cheaper* than more round trips (fewer
calls, and the provider's inference is fast regardless of prompt size within reason). For a local
model, the opposite is often true: prompt processing + generation time scales with token count in
a way that's very noticeable on CPU or modest GPU hardware. When targeting local models, prefer
**more iterations that each do less work** over fewer iterations that each do more — the opposite
of what you'd optimize for against a fast cloud API. Expose this as a tunable
(`batch_size`/iteration budget), not a hardcoded constant, so the same codebase serves both
deployment shapes.

## Timeouts need to be generous and provider-specific

**Symptom observed**: `Local API request failed: ... Read timed out. (read timeout=120)` — a local
model simply needs more than 120 seconds to generate a response for a nontrivial prompt, especially
on first load (model warm-up) or CPU inference.

**Fix pattern**: don't hardcode a single timeout for "the LLM call" across all providers. A cloud
API timing out after 120s usually indicates a real problem; a local model taking 300-600s can be
completely normal. Make timeout a per-provider config value (see `LocalConfig.timeout` in
`src/agents/local_agent.py`), default it generously for local (300s+), and let it be raised
further per deployment (`agents.local.timeout` in `pragma.yaml`) rather than picking one number
that has to work everywhere.

## Checklist when adding/debugging local-model support

- [ ] Is there a hard cap on every list/collection that goes into a prompt (not just "usually
      small")?
- [ ] For each capped item, are you sending only what's needed to *choose*, not everything needed
      to *execute*?
- [ ] Does the HTTP/RPC client timeout to the model server have a provider-specific, generous
      default — not a value copied from a different provider's config?
- [ ] If the model can only see a slice of the full state, does it have enough info to make
      forward progress (e.g. total counts, "N of M shown"), even if it can't see everything?
