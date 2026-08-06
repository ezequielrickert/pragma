# Graph-Based Crawl Tracking

Applies to any agent that moves between discrete states over multiple steps (pages, screens, API
resources) and needs to (a) avoid redoing work, (b) explain how it got somewhere, and (c) not get
stuck.

## Model it as a graph explicitly, not as a flat list of "visited" flags

A crawl is a directed graph: **nodes** are canonical states (pages), **edges** are the
action/component that moved you from one node to another. Treating it as a flat
`{status: pending|finished}` map per URL works until you need to answer "how did the agent get
here" or "what did it click to trigger this" — at which point you're missing the edges entirely.
Track both:

```python
self.routes: Dict[str, Dict[str, Any]] = {}       # nodes: status, label, context
self.graph_edges: List[Dict[str, str]] = []        # edges: from, component, action, to
```

Record an edge every time an action *succeeds* in producing a new state — not on every attempted
action (failed/skipped attempts aren't graph traversal, they're just noise; log those separately,
see [debugging-agent-systems.md](debugging-agent-systems.md)).

## Node identity is the whole game — get canonicalization right or nothing else matters

**Symptom observed**: the crawler oscillated forever between
`https://example.com/admisiones/inscripciones` and `http://example.com/admisiones/inscripciones`
— same page, two different dictionary keys, because the node-identity function didn't strip
scheme. The agent wasn't "stuck" from bad decisions; the graph itself had two nodes where there
should have been one, so "already visited" was never true for the variant it happened to pick.

**Fix pattern**: before adding *any* other loop-prevention logic, verify your node-identity
(canonicalization) function actually collapses every representation of "the same place" into one
key. For URLs: strip scheme, trailing slash, fragment; consider query param ordering and tracking
params (`utm_*`) if relevant to your domain; consider www vs. non-www. Write a test that asserts
two superficially different representations of the same resource produce the same node key
*before* writing any "don't revisit" logic — the loop-prevention logic is only as good as the
identity function underneath it.

## Prefer "decline redundant work" over "override the model's decision"

Two different ways to stop a crawl from looping forever look similar but have very different risk
profiles:

- **Decline (safe)**: before executing an action, check whether it would revisit an
  already-visited node. If so, skip the execution (no page load, no wasted iteration) and tell the
  model clearly next time what's already covered. The model's *choice* is respected; the engine
  just doesn't redo known work.
- **Override (risky)**: detect "no progress for N iterations" via a broader heuristic and
  substitute a *different*, engine-chosen action instead of what the model asked for. This was
  tried in this project and explicitly rejected: a heuristic like "no URL/component change =
  stuck" can misfire on legitimate multi-step interactions (e.g., a real "open dropdown, then
  click a revealed item" sequence looks identical to "stuck" after step one), silently steering the
  agent away from valid exploration paths.

**Update — one narrow, later-added exception, and why it's different from the rejected broad
override above**: a specific *terminal* action (`finish`) is blocked outright when new,
never-shown components were part of what the model was just shown — not substituted for a
different action, just declined, converting the turn into a skipped iteration with an explicit
error instead of ending the run. This is closer in shape to "decline" than to the rejected
"override": it never picks a different action on the model's behalf, it only refuses one specific
action under one precisely verifiable condition (a real, provable "you haven't seen this yet" fact,
not a fuzzy "looks stuck" heuristic), and only for the one action (`finish`) where a wrong guess is
irreversible — unlike a bad click, there's no later turn to recover a premature `finish` in. A
broad "no progress for N turns, so do something else" heuristic remains the wrong call; a narrow,
verifiable, terminal-action-only decline is not the same risk.

```python
# Decline pattern - cheap, precise, never second-guesses the model's actual choice.
if action.kind == "goto" and self._already_visited(action.target):
    print(f"Already visited {self._clean_url(action.target)}, skipping re-navigation.")
    continue  # re-prompt next iteration; no page load spent
```

If you need a broader stuck-detection heuristic, make it opt-in and clearly separate it from the
identity-based decline check above — don't conflate "we know this is redundant" (safe to skip)
with "this looks unproductive by some heuristic" (risky to override).

## Separate the live snapshot from the append-only audit trail

A crawl needs two different kinds of log, and conflating them either loses history or bloats every
read:

- **Live snapshot** (overwritten every step): current status table, fed back into a downstream
  step (e.g. a final synthesis prompt) that only needs to know *current* state, not full history.
  Keep this lean.
- **Append-only trail** (never overwritten): every stage/iteration recorded in order, including
  failed/skipped attempts and the raw text the agent produced — this is what a human opens to
  debug *why* a run behaved the way it did. It should never be read back into the agent's own
  prompts (it grows unbounded); it exists purely for post-hoc inspection.

## Attach a human-readable "why"/"via what" to every edge, not just the raw action

Recording `GOTO https://example.com/x` tells you *where*, not *why* — was it a nav link, a footer
link, a search result? Capture the label/text of the component that triggered the transition
(captured at *discovery* time, when the link was first found on some other page, or at *click*
time from the clicked element's text) and attach it to the edge:

```json
{"from": "example.com", "component": "link \"About Us\"", "action": "GOTO https://example.com/about", "to": "example.com/about"}
```

## A persistent graph store needs an explicit "start fresh" option, or it silently accumulates garbage

**Symptom observed**: a persistent graph backend (surviving across runs, scoped per site) reached
"13/13 visited, 0 pending" on a *brand new* crawl of a site that mints a fresh, random session URL
on every page load (`/o/<random-id>` — no two crawls of it ever share a URL). Every past run's pages
were still marked "visited" under that site's key, forever — none of them would ever be seen again,
but the next run's planning/synthesis steps still read that accumulated history back as real state.

**Why it happens**: cross-run persistence is genuinely valuable for a site with stable, meaningful
routes (resume a large crawl across sessions) — but it's actively harmful for a site whose "routes"
are really just session tokens for the same underlying flow. The graph store has no way to know
which kind of site it's looking at.

**Fix pattern**: give the persistence layer an explicit per-site purge (`clear_site(site)`), and
default to calling it before every run — treat cross-run persistence as something to opt *into*
per-crawl, not an unconditional default:

```python
if config.fresh:  # defaults True
    graph_store.clear_site(site)
```

A process-local/in-memory backend never had this problem (nothing survives past one run anyway),
but implement the purge method uniformly across every backend so callers stay backend-agnostic —
and be aware that "the site" as a lookup key is whatever domain you *requested*, which may not be
the domain you actually end up on after a redirect (`empanad.app` → `www.empanad.app`) - the
purge/lookup key has to match whichever one the rest of your crawl-identity logic actually uses.

## Track per-component interaction state within a node, not just per-node visited status

A node-level `visited: true/false` answers "have I been to this page" but not "what did I actually
do while I was there, and to what." For a page with many interactive elements, that's a real gap: an
edge list only records actions that *changed* page state, not every element shown or every attempt
made, and says nothing about what was shown but never touched.

**Fix pattern**: keep a second structure, keyed by (page, component-identity) rather than just page,
recording whether each component was ever interacted with and the ordered history of what was done
to it:

```python
# {page_url: {component_path: {tag, text, interacted: bool, interactions: [...]}}}
ledger[page][path]["interactions"].append({"action": "fill", "value": "...", "resulting_url": "..."})
```

Two payoffs from the same structure: written out as JSON once a run finishes, it's a durable,
inspectable checklist for a human ("what got touched, what didn't, in what order") that neither the
edge list nor an append-only text log gives directly. And surfaced back into the *next* prompt as a
per-element `(interacted)` marker, it gives the model itself the same "have I already done this"
signal a filled text field's own visible value already provides — but generalized to element kinds
(buttons, options) that carry no state of their own the way a filled input does.

This single field turns a list of URLs into an actual explainable path, and it's nearly free to
render as a diagram (e.g. a Mermaid flowchart) directly from the edge list for a human to skim
without needing any extra tooling.
