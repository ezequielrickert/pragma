# Prompt Engineering for Multi-Step LLM Agents

Applies to any system where one LLM is called at multiple, semantically different points in a
loop (e.g. "make a plan" vs. "decide the next action" vs. "summarize what happened") — not
single-shot prompting.

## Principle 1: Never share a system_instruction across semantically different calls

**Symptom observed**: `_create_plan()` (asks for a multi-step exploration strategy) and the
per-iteration decision call (asks for exactly one `GOTO`/`CLICK`/`FINISH` line) were both passed
the same `system_instruction`. When that instruction was tightened to say "respond with EXACTLY
ONE line, no other text," the *planning* call started collapsing entire plans into a single
`GOTO <url>` line — because the model correctly followed the instruction it was given, which was
wrong for that call site.

**Why it happens**: it's tempting to reuse one "persona" or skill file everywhere an agent needs
*a* system prompt, since it's DRY and feels consistent. But different calls in an agent loop have
different jobs. An instruction that's correct for one job is often actively wrong for another.

**Fix pattern**: give each call site its own system_instruction, even if they overlap 90%. Factor
out only the parts that are genuinely call-site-independent (e.g. domain objective, vocabulary of
valid commands) into a shared base, and layer call-site-specific formatting rules on top *only*
where they're needed:

```python
# Shared: what the agent is doing and what commands exist.
BASE_SKILL = "You are exploring a website. Commands: GOTO <url>, CLICK <n>, FINISH."

# Only the decision loop gets the strict format rule - the planning call does not.
DECISION_FORMAT = "Respond with EXACTLY ONE line: no explanation, no markdown."

plan = agent.generate(plan_prompt, system_instruction=BASE_SKILL)
action = agent.generate(action_prompt, system_instruction=f"{BASE_SKILL}\n\n{DECISION_FORMAT}")
```

**How to catch this in review**: grep for every `system_instruction=` call site in an agent loop
and list what each one is actually asking for. If two call sites share an instruction, verify by
literally reading both prompts back to back — would a rule good for one make sense for the other?

## Principle 2: A skill/persona file's content must match the call site it's injected into

**Symptom observed**: a skill file named `archaeology-progress-tracker` contained instructions to
"Update PROGRESS.md with: 1. Status summary 2. Table 3. Log of actions." It was injected into the
*action-decision* system_instruction, alongside the `GOTO`/`CLICK`/`FINISH` command format. The
model — faced with two different jobs in one prompt — did the more concrete, template-shaped one
(write a progress table) instead of emitting an action. Every iteration failed the same way.

**Why it happens**: skill files accumulate over a project's life, sometimes written for a design
that later changed (in this case, PROGRESS.md ended up being written mechanically by Python, never
by the LLM — but the skill file describing "how to write PROGRESS.md" was never removed from the
prompt it was originally paired with). Nobody audits *which prompt calls consume which skill
file* as the codebase evolves.

**Fix pattern**: when you add or repurpose a skill/persona file, trace every place it's loaded and
confirm the file's content is instructions *for that exact call*, not leftover guidance for a
different phase. When in doubt, don't load a skill file "just in case it helps" — an unused,
correctly-scoped prompt beats an over-included, conflicting one.

## Principle 3: If you generate an artifact, you must consume it — or don't generate it

**Symptom observed**: `_create_plan()` produced a real exploration plan, which was logged to the
progress file... and then never read again. The execution loop started from scratch with no
memory of the plan. The plan-creation LLM call was pure waste — extra latency and cost for zero
effect on behavior.

**Fix pattern**: after adding a "planning" or "reflection" step that produces text, follow the
data: does anything downstream actually read that text and change behavior because of it? If not,
either wire it in (e.g. carry a `plan_summary` forward as a `Plan: ...` line in every subsequent
prompt) or remove the step. A generated-but-unused artifact is a bug, even though nothing crashes.

## Principle 4: Prefer indexed/enumerated references over asking the model to reproduce strings

**Symptom observed**: the agent was asked to `CLICK <full CSS path>`, e.g.
`body > header > header:nth-of-type(1) > div > div:nth-of-type(2) > ... > a`. This is exactly the
kind of long, structurally-repetitive string that small/local models corrupt, truncate, or
hallucinate variations of. It also bloated every prompt (see
[local-and-small-model-constraints.md](local-and-small-model-constraints.md)).

**Fix pattern**: whenever the model needs to refer back to one of several items you just showed
it, give each item a short number and have the model answer with the number, not the item itself:

```
Clickable elements on this page:
[1] <a> 'About'
[2] <button> 'Sign up'

Action: CLICK <element number from the list above>
```

The program resolves `CLICK 2` back to the real selector via an index built fresh each iteration —
the model never has to reproduce anything longer than a small integer. This is strictly easier for
weak models to get right, and it shrinks the prompt (see next doc).

**Update — the literal-selector fallback below was later removed, on purpose:** this doc originally
recommended keeping a fallback path (treat an unresolvable target as a literal CSS selector, or
match by visible text) for a stronger model that might improvise anyway. In practice this made
failures *more* confusing, not less: a model that invented a selector instead of using a shown
index got a plausible-looking but wrong action silently accepted, instead of a clear, immediate
rejection it could learn from. The fix was the opposite of "keep a lenient fallback" — reject any
unresolvable ref outright and say so in the next prompt's error-feedback line (see Principle 5):

```python
def _resolve_ref_selector(self, ref):
    if ref is not None and ref in self._dna_index_map:
        return self._dna_index_map[ref]["path"]
    raise ValueError(f"Unknown element ref: {ref!r} - use a number from the Clickable elements list")
```

General lesson: a permissive fallback for "in case the model does something clever" usually isn't
worth it once you have a working error-feedback loop — a clear rejection the model can react to on
the next turn beats a silent guess that might be wrong in a way nobody notices.

## Principle 5: State negative constraints in the prompt *and* enforce them mechanically

**Symptom observed**: the prompt said "do NOT GOTO this URL again," but nothing in the code
actually stopped a repeat GOTO from executing. A confused or redirect-looping model ignored the
instruction and the engine dutifully re-navigated every time.

**Fix pattern**: a prompt instruction is a *request*, not a guarantee. For any constraint that
would be genuinely bad to violate (redoing expensive work, revisiting a dead end), add a cheap
check in code that declines to act on a violation rather than trusting the model to self-police.
See [graph-based-crawl-tracking.md](graph-based-crawl-tracking.md) for where to draw the line
between "decline redundant work" (safe) and "override the model's decision" (risky).

**A second instance of the same principle, escalated**: an *informational* nudge (a prompt line
saying "N new elements just appeared, investigate before finishing") wasn't enough on its own — a
small local model concluded a run anyway, immediately after a page changed substantially (3 → 11
components, same URL) without looking at any of the new content. Text the model can silently ignore
isn't a mechanical constraint, no matter how clearly it's worded. The fix escalated from "inform" to
"block": the specific terminal action (`finish`) was rejected outright when new, never-shown
components were part of what the model had just been shown, converted into a skipped turn with an
explicit error instead of ending the run. This is a narrower, more justified version of "override"
than the broad heuristic [graph-based-crawl-tracking.md](graph-based-crawl-tracking.md) warns
against — see that doc's updated "Prefer decline over override" section for why blocking one
specific, verifiable-condition, terminal action is a different risk profile than substituting a
different action for whatever the model chose.

## Principle 6: For a weak/small model, prefer deterministic always-shown signals over optional on-demand ones

**Symptom observed, repeatedly**: several pieces of guidance were first built as something the
model could *ask for* (a `help(topic)` action returning fuller docs on demand) or as a *hint* it
could act on if it noticed. Both consistently underperformed a plainer alternative: computing the
same information deterministically in code and putting it directly in every relevant prompt,
unconditionally. A field's current value, whether a combobox's options are already visible, whether
a submit button is actually ready to be clicked, whether an element has already been interacted
with — all of these ended up as **always-rendered facts computed from real state**, not as
something gated behind the model choosing to ask or independently noticing.

**Why it happens**: an optional lookup adds a second point where a weak model's tool-calling can
fail (see [local-and-small-model-constraints.md](local-and-small-model-constraints.md) on native
tool-calling reliability) and a second decision it can simply skip. A hint buried in prose competes
with everything else in the prompt for attention a small model may not reliably allocate.
Information the model *needs* to act correctly this turn is more reliable as an unconditional fact
than as something contingent on the model's own initiative.

**Fix pattern**: reserve on-demand/optional lookups (`help`, a docs API) for genuinely deep
background that would be wasteful to include on every single turn — the "why", not the "what's true
right now." Compute and inject anything the model needs to make *this turn's* decision correctly,
every time, as a short deterministic line derived from real state:

```python
if any(c.get("input_type") == "submit" for c in shown_components):
    unfilled = [i for i, c in enumerate(shown_components, 1) if is_fillable(c) and not c.get("value")]
    line = (f"Do not click submit yet - field(s) {unfilled} still show no value."
            if unfilled else 'Every visible field has a value - click submit next.')
```

This costs a little prompt space on every turn, in exchange for not depending on the model
remembering to ask, or noticing a subtle change on its own — a trade worth making for anything the
model would otherwise get wrong by default.
