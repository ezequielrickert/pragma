# Debugging Agent Systems: A Methodology

Applies whenever an autonomous agent loop "misbehaves" — stuck, invalid output, no progress, or
just wrong — and it's not immediately obvious whether the model, the prompt, or the code is at
fault. This is the diagnostic process that found and fixed every bug documented in the other wiki
pages; read this first when something looks broken.

## Don't blame the model first

Every "the model is being dumb" symptom encountered while building this project turned out to be a
code or prompt bug, not a model-competence problem:

| Symptom | Looked like | Was actually |
|---|---|---|
| Every response was an invalid action | Weak model can't follow instructions | Conflicting system_instruction (two jobs, one prompt) — see prompt-engineering doc |
| Agent revisits the same page forever | Weak model keeps making the same bad choice | URL scheme not normalized — two dict keys for one page — see graph-tracking doc |
| Agent keeps clicking the same broken thing | Weak model fixates | Non-unique generated selector, silently failing every time — see browser-automation doc |
| Iteration takes 600+ seconds | Weak/slow model | Verbose per-item data (full CSS paths, class strings) blowing up prompt size — see local-model doc |
| Agent had "nothing to click" after opening a dropdown/combobox | Weak model can't figure out the widget | Discovery selector missed the whole family of ARIA-role custom-widget elements — 22 real options existed, none discoverable — see browser-automation doc |
| Agent filled a field with junk / left it empty despite a "required" schema field | Weak model ignoring the tool schema | Native tool-calling silently omitted the parameter anyway — schema `"required"` isn't enforced by the model's own chat template — see local-model doc |
| Agent concluded research immediately after a page changed substantially | Weak model not caring / done too early | An *informational* nudge alone doesn't mechanically stop anything — needed an actual block, not just a hint — see prompt-engineering doc (Principle 5) |
| Server logs flooded with cryptic auth warnings | Infra/credentials misconfigured | Tests never loaded `.env` at all — a real secret existed but the check that would have used it never saw it |

The pattern: **a plausible-sounding "the model just isn't good enough" story will stop you from
finding the actual bug.** Treat that explanation as a last resort, only after the checklist below
has been exhausted.

## Checklist, in order

1. **Read the raw, literal output/error text** — not a summary of it, the actual string. Different
   root causes produce different exact error text, and guessing from a vague symptom description
   ("it's stuck", "clicks don't work") will send you down the wrong path. `strict mode violation:
   resolved to 3 elements`, `element is not visible`, and `Timeout 5000ms exceeded` are three
   different bugs needing three different fixes, even though a user might describe all three as
   "the click doesn't work."
2. **Check for shared/conflicting prompts first** — if the same `system_instruction` (or prompt
   template) is used at more than one call site, read both call sites' *actual purpose* side by
   side. This alone explained two separate reported bugs in this project.
3. **Check for silently swallowed errors** — grep the action/tool-execution layer for
   `except Exception` blocks that log-and-continue instead of re-raising. A swallowed error makes
   a real failure indistinguishable from a legitimate no-op to every layer above it, and will
   masquerade as "the model chose to do nothing useful."
4. **Check identity/normalization functions** — anywhere you dedup, cache, or check "have I seen
   this before," verify the identity function actually treats equivalent inputs as equivalent
   (scheme-stripped URLs, case-insensitive keys, etc.). A broken identity check looks exactly like
   an infinite loop from bad decisions.
5. **Only after 1-4**: consider whether the model itself is actually undersized/undertrained for
   the task, and address that on its own terms (bigger model, few-shot examples, structured output
   enforcement) — don't reach for this before ruling out the above.

## When the failure involves unfamiliar real-world specifics, go to the real target *first*

The scripted-fake technique below is for confirming and regression-testing a hypothesis you already
have. It can't help you *form* one when the actual failure mode lives in specifics you don't know
yet — you can't write a fake that accurately reproduces a real site's markup without first knowing
what that markup actually is. A combobox rendering its options as `<div role="option">` instead of
`<button>`, a `required` attribute that's `false` on every field on a real site regardless of what's
actually required, a native tool call silently missing a parameter — none of these were guessable
from first principles; every one was found by driving the real target directly (the actual scraper
against the actual live URL, in a throwaway script) and reading back exactly what came out:

```python
scraper = PlaywrightScraper()
state = scraper.navigate(url)
print(state.components)  # what does the tool actually see, right now, for real?
```

Once that reveals the actual failure mode, encode it as a scripted fake (below) for the permanent
regression test — the two techniques are sequential, not alternatives: real target to discover the
unknown shape of the bug, scripted fake to lock the fix in place forever afterward.

## Reproduce with a deterministic, scripted fake — not just "try it again on the real site"

Every fix in this project was verified with a scripted, fully deterministic fake agent (returns a
fixed sequence of canned responses) plus a stub or fake scraper, run inside a unit test:

```python
class ScriptedAgent(Agent):
    """Returns each response in `script` in order, then FINISH forever after."""
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0
    def generate(self, prompt, system_instruction=None):
        r = self.script[self.calls] if self.calls < len(self.script) else "FINISH"
        self.calls += 1
        return r
```

This buys three things a real end-to-end run against a live site and a live model can't:
- **Reproducibility**: the exact same bug happens every time, in milliseconds, with no network or
  live model needed.
- **Isolation**: you can construct the *exact* problematic sequence (e.g. "GOTO A, GOTO A again")
  without depending on a real model happening to produce it.
- **A permanent regression test**: once the scripted scenario reproduces the bug, the same test
  (asserting the fix's behavior) stays in the suite forever, catching a reintroduction of the same
  bug by a later, unrelated change.

## After every fix: write the regression test for the *specific* observed symptom, not a generic smoke test

A generic "does the happy path still work" test won't catch a specific bug coming back. Write the
test to reproduce the *exact* failure mode reported (the exact malformed input, the exact repeated
action, the exact hidden-element markup) and assert the specific fixed behavior. See
`tests/test_imports.py` in this repo for examples — each bug documented in this wiki has a
corresponding test named after the symptom, not after the fix.

## When you fix something, ask "does this fix conflict with an earlier fix?"

This bit the project directly: a fix to make action-decision responses strictly one line was
applied to a *shared* system_instruction, which broke the planning call that needed prose. The fix
itself was correct in isolation — the bug was not checking whether the change had a second,
unintended blast radius. Before shipping a prompt/instruction change, grep for every other call
site that shares the thing you're changing.
