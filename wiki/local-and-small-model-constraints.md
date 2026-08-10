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

**Update — this exact bug reappeared in a different generator, because the discipline was never
ported when the old one was replaced:** `prd_generator.py`'s `SimplePRDGenerator` (the source of
the `batch_size` fix above) was deleted during the crawl4ai migration and replaced by
`GraphPRDSynthesizer` (`src/generators/graph_prd_synthesizer.py`). Its **final aggregate call**
(`synthesize()` — one `agent.generate()` combining every page's full narrated component catalog
plus the entire Mermaid navigation graph into one prompt, asking for one completion containing the
whole output document) had no cap and no `try/except` at all. Confirmed live on empanad.app: 4/4
runs hit truncation even at `max_tokens: 8192`, crashing the whole run with **zero** `docs/` output
— despite the crawl itself completing successfully every time and all the rich data sitting safely
in Neo4j the whole time, simply never read back into a document because this one call died first.
The earlier fix capped a per-*iteration* prompt in a loop; this generator's bug was in the
*aggregate/reduce* stage of a multi-stage pipeline — the one call that combines everything a whole
run produced — which is a different call shape but the identical underlying mistake ("this one will
surely fit"). **Fix pattern, generalized**: when a generator has a map stage (bounded, one call per
item — this one already had that, correctly, via `_narrate_page_catalog`) *and* a reduce stage (one
call combining every map result), the reduce stage needs its own cap just as much as the map stage
does — don't assume that because the per-item calls are individually bounded, their aggregate is
automatically small too. Extend map-reduce to three stages when the reduce input itself can grow
unboundedly with corpus size: map → batch-summarize (bounded chunks of map outputs) → reduce (one
small call over the already-condensed batch summaries, never the raw per-item data again). Also
worth doing regardless of prompt size: never ask the model to reproduce something you can already
render deterministically (here, a Mermaid graph) verbatim inside its own completion — that spends
real output-token budget on the single highest-risk call for literally nothing; render it in code
and append it to the output afterward instead.

## `max_tokens` (output budget) and context window (input capacity) are two different limits — don't fix one by shrinking the other

**Symptom observed**: `RuntimeError: Response truncated: the model hit max_tokens before finishing
(finish_reason: 'length')` (`LocalAgent._raise_if_truncated`, `src/agents/local_agent.py`) was
initially proposed to be fixed with a RAG/retrieval layer — feed the model a smaller, retrieved
subset of the corpus instead of everything, on the reasoning "the model has a small token limit."

**Why that doesn't work**: `finish_reason: "length"` (the OpenAI-compatible signal this error
checks) means the **response** hit its `max_tokens` cap mid-generation — an *output*-side limit,
configured explicitly (`agents.local.max_tokens`/`LOCAL_MAX_TOKENS`). It has nothing to do with how
much input the model can accept; a model's context window (input + output combined capacity) is a
separate property of the model/server, not something `max_tokens` controls at all. RAG (or any
other input-shrinking technique) reduces prompt size — it cannot make a response finish inside a
fixed *output* budget, because the two are unrelated knobs. If a call is failing on
`finish_reason: "length"`, the fix has to either raise/unset `max_tokens` itself, or reduce how much
*output* the call is asking the model to produce (see the "Context window overflow" update above for
a real case where that was the actual problem — a single call asked for an entire multi-section
document in one completion) — never a change aimed at input size alone.

**Fix pattern**: before reaching for any fix, read which side of the request the error actually
names. `finish_reason: "length"` / "hit max_tokens" → output-side, fix output ask-size or the
`max_tokens` config. A context-length/`n_ctx`/400-error shape (see "Context window overflow" above)
→ input-side, fix what's being sent in the prompt. Don't assume they're the same problem because
they both smell like "the model ran out of room" — the code fix and the config fix live on opposite
sides of the request.

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

## Native tool-calling: a "required" schema field is not a guarantee the model fills it

**Symptom observed**: a local model's native `tool_calls` response for a `fill(ref, value)` action
came back as `{"ref": 1}` — `value` simply absent, even though the OpenAI-style function schema
listed it under `"required"`. Filling `""` every time is worse than a visible failure: it looks
like a real action ran (a new page state came back) while never actually entering anything, which
produced an infinite loop between a toggle control and a field that silently stayed empty forever.

**Why it happens**: `"required"` in a JSON schema is a hint most cloud APIs enforce server-side,
but a local model's own chat template decides what it actually emits — nothing forces compliance
in general, and a small model's tool-calling is exactly where you should expect it to be loosest.

**Fix pattern**: never trust that a "required" parameter arrived — validate on the receiving end,
and prefer *recovering* over *erroring* for parameters you can reasonably synthesize. If the target
element's own metadata (a label, placeholder, `name`, input type) is available, generate a sensible
fallback value from it rather than silently sending an empty string or aborting the run:

```python
if not action.value:
    action.value = generate_value_from_field_metadata(target_component)
```

Mutate the actual action object (not just a local variable) so anything logged or read downstream
reflects what was actually sent — a fallback that only lives in a local variable can silently never
reach the log a human reads to debug the run.

## Constrain parameters structurally (JSON-schema `enum`), not just with prose in a description

**Symptom observed**: a tool parameter's valid values were spelled out only as prose inside its
`description` string ("string - one of: goal_overview, ref_semantics, ..."). The model hallucinated
a plausible-but-wrong value anyway ("navigation" instead of the real `navigate_usage`) — prose
inside a description field is not a constraint, just more text competing with everything else in
the prompt for the model's attention. Separately, the compact text-fallback rendering used for
backends without native tool-calling support didn't even render parameter descriptions at all
(only parameter *names*) — so on that path, the model never saw the valid values in the first
place, regardless of how they were phrased.

**Fix pattern**: for a closed set of valid values, use a real JSON-schema `enum` on the native
tool-calling path, not prose:

```python
properties["topic"]["enum"] = ["goal_overview", "ref_semantics", "navigate_usage", ...]
```

And on the text-fallback path, give the enum its own explicit, always-rendered line — don't rely on
a per-tool description string to carry it, since some renderers of "available tools" may not even
surface parameter descriptions at all:

```
Valid help topics (must match exactly): goal_overview, ref_semantics, navigate_usage, ...
```

Test both code paths independently — they can (and did, here) diverge silently, since a fix
verified against one path's actual output can leave the other completely unfixed.

## Checklist when adding/debugging local-model support

- [ ] Is there a hard cap on every list/collection that goes into a prompt (not just "usually
      small")? Including any *reduce*/aggregate stage that combines other calls' outputs — a
      bounded map stage doesn't make its reduce stage automatically bounded too.
- [ ] Before fixing a "ran out of room" error, did you check which side it's actually on -
      `finish_reason: "length"`/`max_tokens` (output) vs. a context-length/`n_ctx` error (input)?
      They need opposite fixes.
- [ ] For each capped item, are you sending only what's needed to *choose*, not everything needed
      to *execute*?
- [ ] Does the HTTP/RPC client timeout to the model server have a provider-specific, generous
      default — not a value copied from a different provider's config?
- [ ] If the model can only see a slice of the full state, does it have enough info to make
      forward progress (e.g. total counts, "N of M shown"), even if it can't see everything?
- [ ] For every tool parameter marked "required" in a schema, is there a fallback if the model
      omits or empties it anyway — not just a schema annotation you're trusting it to honor?
- [ ] For every closed-set parameter (an enum of valid values), is the constraint structural
      (JSON-schema `enum`) on every code path that can produce a tool call, not prose in one?
