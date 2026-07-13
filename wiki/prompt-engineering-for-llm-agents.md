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
weak models to get right, and it shrinks the prompt (see next doc). Keep a fallback path (treat
the target as a literal selector, or match by visible text) for stronger models that might
improvise anyway — don't make the fallback the primary path.

## Principle 5: State negative constraints in the prompt *and* enforce them mechanically

**Symptom observed**: the prompt said "do NOT GOTO this URL again," but nothing in the code
actually stopped a repeat GOTO from executing. A confused or redirect-looping model ignored the
instruction and the engine dutifully re-navigated every time.

**Fix pattern**: a prompt instruction is a *request*, not a guarantee. For any constraint that
would be genuinely bad to violate (redoing expensive work, revisiting a dead end), add a cheap
check in code that declines to act on a violation rather than trusting the model to self-police.
See [graph-based-crawl-tracking.md](graph-based-crawl-tracking.md) for where to draw the line
between "decline redundant work" (safe) and "override the model's decision" (risky).
