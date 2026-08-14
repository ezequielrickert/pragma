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

**Update — the finish-blocking condition above ("never-shown") was later found to be too weak,
and had to become "never-interacted-with":** the mechanism (decline, don't override) was right;
the specific *fact* it was checking wasn't. A component the model had been *shown* once — in a
numbered list it glanced at — counted as "covered," even if the model never actually clicked, filled,
or submitted it. A real run exposed this directly: the model filled one field on a page, was shown
two other real components in that same prompt, and called `finish` on the very next turn — the
guard let it through because both components had technically been "shown," which is all the
original condition checked. "Shown" only proves the model's prompt *contained* the component; it
proves nothing about whether the model did anything with it. The fix: gate `finish` on whether each
component's persisted `interacted` flag (see the per-component ledger below) is `True`, not on
whether its path has ever appeared in a rendered list. This also fixed a second instance of the same
mistake at the boundary of a run: the check used to be skipped entirely on the very first prompt of
a run ("everything's trivially new on turn one, that's not itself suspicious") — but "has this ever
been looked at" is exactly as unanswered on turn one as on any later turn; there is no legitimate
reason for turn one to be exempt from a check whose actual job is "was this acted on," not "is this
new."

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

**Update — this project's own per-page markdown snapshot violated this principle for a long time,
because "one snapshot per page" was the wrong mental model:** `CrawlDebugLog.save_page_markdown`
(`spiders/browser/debug_log.py`) was built overwrite-only, on the reasoning that a page's markdown
snapshot is a "live snapshot" concept — reasonable-sounding, and correct for the case of a literal
page *revisit*. What that reasoning missed: `save_page_markdown` isn't called once per page visit,
it's called once per **interaction** within a session (`discover_page`, every `_interact`, every
`resync` — see `Crawl4AICrawler._save_markdown`'s call sites). A single page visit with, say, 40
interactions saves the same file 40 times. If interaction #12 reveals a component's items (a rich,
diagnostically valuable DOM state) and interaction #13 is a completely unrelated click elsewhere on
the page, the overwrite silently destroys interaction #12's snapshot with no trace it ever existed —
confirmed live on austral.edu.ar as exactly the symptom a human would describe as "the states are
being stepped on... if a component with items is discovered, then another iteration steps over what
was written."

**Fix pattern**: keep the overwrite-only file for its real, legitimate use (quick "what does this
page look like right now" convenience), but add a second, append-only companion file that every
`save_page_markdown` call also writes to, never overwritten:

```python
def save_page_markdown(self, url: str, markdown: str) -> str:
    # Live: overwritten every call, current-content convenience.
    write(pages_dir / f"{slug}.md", markdown)
    # History: appended every call, never overwritten - the actual
    # append-only audit trail for this artifact.
    append(pages_dir / f"{slug}.history.md", f"\n\n---\n\n<!-- [{timestamp()}] -->\n\n{markdown}")
```

**General, reusable lesson**: "does this event happen once per logical unit of work" is the
question to ask before deciding an artifact is safe to make overwrite-only — it's easy to reach for
"live snapshot" as soon as the *key* (a URL, a page) is stable across calls, without checking
whether the *call frequency* is actually higher-resolution than that key implies. Any artifact
that's saved more often than the granularity a human would naturally think of it at ("once per
page") needs the append-only treatment, or every intermediate state between the first save and the
last becomes unrecoverable.

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

**Update — `fresh` only fixes cross-run staleness; a session-token site still needs a *within-run*
bound too, and this is a separate mechanism, not the same knob:** confirmed on the same site
(empanad.app mints a fresh `/o/<random-hash>` URL on essentially every top-level visit - 10 distinct
tokens observed across two runs). `fresh: true` correctly stops old runs' dead nodes from polluting a
new run, but it does nothing about *this* run's own frontier: every newly discovered token is a
genuinely distinct `clean_url()` identity (correctly so - they're different orders), so an unbounded
crawl treats each one as a brand-new page forever and never converges, burning a full interaction
pass on what's structurally the same page every time (see
[crawl4ai-integration-pitfalls.md](crawl4ai-integration-pitfalls.md)'s stale-selector entry for what
that wasted pass actually looked like). `www.` vs. bare-domain is the same node-identity gap in
miniature: the log showed `empanad.app` and `www.empanad.app` tracked as two separate keys, each
independently re-triggering the site's per-visit redirect - `clean_url()` now also strips a leading
`www.`, same rationale as stripping scheme.

**Fix pattern**: add a second, coarser identity function layered on top of the real one - collapse
any path segment that looks like an opaque generated token (long, mixed alphanumeric - real slugs
like `admisiones` don't match) into a placeholder, and use *that* to bound how many instances of
"the same kind of page" one crawl will fully visit:

```python
def route_shape(url: str) -> str:
    # example.com/o/<hash-a> and example.com/o/<hash-b> -> same route_shape,
    # even though clean_url() correctly keeps them as distinct real nodes
    ...

if route_shape_visit_count[route_shape(url)] >= max_visits_per_route_shape:  # default 1
    skip_enqueue()  # real slugs never hit this - only repeated opaque-token shapes do
```

Keep this a *separate* counter/knob from the real per-node `visited` tracking above - conflating "is
this the same node" with "is this the same *kind* of node" would make a real, distinct page wrongly
look like a duplicate the moment its path happens to contain a long token-shaped segment for an
unrelated reason (a product SKU, a slug that's just long).

**Update — "never for real identity" above was too strong; the real requirement is narrower: never
conflate route-shape identity with *physical-navigation* identity, but canonical *storage* identity
is exactly what a session-token site needs `route_shape` for:** the bounding fix above stops the
frontier from growing forever, but a human looking at the resulting PRD/component tree for
empanad.app still saw one separate, near-duplicate page node per `/o/<hash>` instance actually
visited - two order-confirmation screens they immediately recognized as *one* screen. The fix is to
use `route_shape(url)`, not `clean_url(url)`, as the `page_key` for every GraphStore/tracker write
(component ledger, inventory, page-finished status) - components already interacted-with on one hash
instance are then correctly recognized as covered on the next, and both visits merge into one graph
node. The one identity check that must stay on the *literal* URL, always: whether the live browser
session physically navigated. Collapsing that one too would mean a real navigation between two
same-shaped hash instances (e.g. a "start a new order" button) stops being detected as navigation at
all - the pass would keep issuing clicks built for a page the session already left, reintroducing
[crawl4ai-integration-pitfalls.md](crawl4ai-integration-pitfalls.md)'s very first documented bug
("Execution context was destroyed"). Two identities, two different questions, never merged into one
variable:

```python
page_literal = clean_url(state.url)   # what the browser session physically did - navigation check
page_key = route_shape(state.url)     # what a human calls "this page" - GraphStore/tracker key
...
if clean_url(new_state.url) != page_literal:  # real navigation - literal, never route_shape
    ...
```

## A same-URL DOM change can be a full screen replacement, not just a reveal - URL-only identity misses it entirely

**Symptom observed**: on a real crawl of empanad.app, clicking "start order" never navigates
(`navigated: False` in every single event of the debug log) - but the component count swings
3 -> 26 -> 0 -> 11 across one continuous session, and the saved page markdown collapses to
essentially nothing mid-pass. A human looking at the two screens (the landing page, and the order
form that appears after the click) immediately calls them two different screens - but every node
identity this codebase tracks (`page_literal`/`page_key`, both derived from the URL - see the
"Two identities, two different questions" entry above) is identical before and after, because the
URL genuinely never changes on a client-routed SPA screen transition.

**Why it happens**: the existing "same-URL DOM change" handling (the reveal-merge path -
`find_revealed_options` + append-to-frontier) was built for one specific shape: a dropdown/popover
opening, where nearly everything from the prior snapshot survives and a few new items appear. It has
no way to tell that shape apart from "the whole screen was replaced" - both are, from the code's
point of view, just "some new components exist that weren't there a moment ago on the same URL." A
full-screen SPA transition silently took the reveal-merge path too, and every one of these
human-distinguishable screens landed in one graph node's component ledger.

**Fix pattern**: add a third identity question, layered on top of the two already established
above (`page_literal` for physical navigation, `page_key`/`route_shape()` for canonical storage
identity) - a `state_key` for "is this still the same *screen*," answered by component-identity
overlap between the immediately-preceding snapshot and the post-interaction one, since the URL
gives no signal at all here:

```python
def _component_overlap_ratio(before, after) -> float:
    before_ids = {_component_identity(c) for c in before if c.get("visible")}
    if not before_ids:
        return 1.0  # nothing to compare against - never trigger the riskier branch
    after_ids = {_component_identity(c) for c in after if c.get("visible")}
    return len(before_ids & after_ids) / len(before_ids)

# Below threshold (default 0.5) - most of the prior screen is gone, this is
# a transition, not a reveal. Treat it like a real navigation to a NEW node:
# record_navigation_edge(old_key, new_key, trigger_path, action), then a
# fresh record_page_arrival/record_inventory/record_text_content under
# new_key - not merged into old_key's ledger.
```

`state_key` itself is derived from a hash of the new screen's own component-identity signature, not
a raw incrementing counter - the same "canonical identity, not an arbitrary counter" reasoning
`route_shape()` already applies to session-token URLs elsewhere in this doc, so re-crawling the same
transition from a different session (or a different order) still collapses to one node instead of
minting a new one every time.

**The old node's completion status must stay honest, and there is nowhere to send a "resume" pass**:
unlike an ordinary navigation interruption (see
[crawl4ai-integration-pitfalls.md](crawl4ai-integration-pitfalls.md)'s "must stop that page's work
immediately" entry), there is no follow-up visit that can ever finish draining a node that got
abandoned mid-transition - a fresh navigation to that same physical URL reloads the SPA's *initial*
landing screen, not the mid-flow state the pass was on. So the old (or an intermediate) node is only
marked `Finished` if the transition happened to consume its very last remaining frontier item;
otherwise it's left exactly as `Pending` forever, honestly signaling "not fully explored" rather than
fabricating a resumable state that doesn't exist. The pass itself doesn't stop, though - unlike a
physical navigation, the DOM already reflects the new state (no re-navigation needed), so the same
live session just keeps going, now acting against the new node's own frontier.

**How to catch this in review/testing**: the reveal-merge path and the transition path have to
coexist without either swallowing the other's case - test both directions: an ordinary reveal
(construct a fixture where a click's resulting snapshot keeps nearly everything from before and adds
a few items) must NOT produce a state transition, and a near-total replace (a fixture where a click's
resulting snapshot shares almost nothing with the prior one) must NOT get silently merged into the
old node's ledger the way the reveal case correctly is.

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

**Update — a write-only ledger doesn't help discovery; it has to be consulted, and consulted
without a quality filter that quietly excludes real elements:** the ledger above was originally
built and populated correctly, but nothing ever *read it back* to decide what to explore next — it
was pure logging, checked by nothing. The fix wasn't the ledger itself, it was wiring the completion
guard (see "Prefer decline over override," above) and the next-turn element-priority logic to
actually query it, and to keep querying it across page revisits and even across separate runs
against a persisted backend (a component genuinely interacted-with in a *previous* run must stay
deprioritized on turn one of a new run against the same site — an in-process-only "have I shown
this" set can never know that).

A second trap on the same code path: if your discovery layer has a two-tier design — a reliable
primary selector (native tags, ARIA roles) plus a noisier last-resort fallback for elements with no
semantic markup at all (see [browser-automation-pitfalls.md](browser-automation-pitfalls.md)'s
`cursor: pointer` fallback) — don't let a "reduce noise" filter on the *fallback* layer bleed into
your *completion* check. The fallback layer is frequently the **only** layer that finds anything at
all on a page built with a component library (custom `<div>`-based buttons/pickers/menus with no
native tag or role) — excluding it from "is this page fully explored" makes those pages look
complete the instant *any* semantic-layer element is touched, regardless of how many real,
clickable, library-built components sit right next to it, untouched. If a layer distinction exists
for ranking/noise-reduction purposes, keep it — but give the completion/coverage check its own,
separate, inclusive view that doesn't inherit that filter by default.

**Update — a "rich write, thin auto-create" split silently produces ghost nodes if the rich write
isn't re-invoked for every new snapshot, not just the first:** a common, reasonable-looking API
shape is one method that writes a component's full descriptive facts (tag, text, role, type — call
it the *inventory* writer) plus a separate method that marks a component interacted-with, which
auto-creates the node with every descriptive field blank if it doesn't already exist (so an
interaction can still be recorded even if inventory-writing was skipped for that specific path).
This is a sound design for the case it's meant for (an interaction landing on a path genuinely never
seen before) — but it silently produces a **ghost node** for a much more common case: a same-page
interaction (opening a dropdown, expanding a menu) reveals components that only exist in a *later*
discovery snapshot, and if the inventory writer is only ever called once per page visit (the
*initial* snapshot) rather than once per snapshot, every revealed component's interaction gets
recorded through the thin auto-create path instead — real text/type/role never written, `interacted:
true`, every other field blank. Confirmed on a real, live crawl: dozens of components (an entire
revealed dropdown's worth of real choices) persisted as nameless, typeless nodes — the *only* visible
symptom to a human looking at the store was "most nodes are empty," which reads exactly like a
`wiki/local-and-small-model-constraints.md`-style "the extraction must be broken" story, except the
extraction script itself was fine; it just wasn't being asked to run again for the new snapshot.

**Fix pattern**: call the inventory writer once per *discovery snapshot*, not once per *page visit*
— any time your interaction loop re-discovers state after an action (the same-page-reveal branch a
loop like this already has), treat that as a fresh, equally-authoritative snapshot and inventory it
the same unconditional way the very first one was:

```python
# Same-page DOM change after an interaction - re-inventory it exactly like the
# initial snapshot, not just record the interaction that produced it.
if new_key == page_key:
    sink.record_inventory(page_key, new_state.components, new_state.links)
    # ...then diff/append newly-revealed items to this pass's frontier
```

**How to catch this in review/testing**: don't just test that an interaction gets recorded — test
that a component *only reachable via a same-page reveal* ends up with real, non-blank descriptive
fields in the persisted store, not just `interacted: true`. A test built around "was this path
touched" alone can pass while every field on that path is silently empty.

## Bounding per-node work: internal rounds within one session, not requeue-via-re-navigation

**Symptom observed**: a page with more interactive components than a configured per-visit budget
got the first N interacted with, then was marked fully done anyway — the rest were silently dropped,
permanently, in that run and any future resumed one. The first fix attempt made a mid-air
navigation-shaped requeue (pop the URL, revisit it, expect to pick up where the last pass left off)
handle this the same way an actual cross-page navigation is requeued — and looked reasonable until
its own regression test caught it: on the "resumed" pass, the trigger that would reveal the rest of
the page's components was *already marked interacted* from the first pass, so it got skipped by the
consult-before-act check — but a fresh navigation had reset the DOM back to its pristine, unrevealed
state, so nothing downstream of that trigger was ever reachable again. The page looked "in progress"
but had actually permanently stranded everything past whatever the first pass touched.

**Why it happens**: a real navigation (even to the identical URL) reloads the document from scratch
— any DOM mutation a same-page interaction produced (a revealed menu, an expanded panel) is gone,
back to first-load state. "Requeue the URL for another pass" and "continue working on this page"
are *not* the same operation unless the second one reuses the exact same live session with no
navigation in between. A generic requeue mechanism built for one reason (a genuine cross-page
navigation, where a fresh load is exactly correct) is not safe to reuse for a different reason
(more budget needed on the *same* page) just because both symptoms look like "this pass ended
early."

**Fix pattern**: keep the two cases structurally separate. A real navigation interruption still
gets the requeue-via-fresh-visit treatment (there's no "same session" left to resume anyway — see
[crawl4ai-integration-pitfalls.md](crawl4ai-integration-pitfalls.md)'s navigation-interruption
entry). Running out of per-visit budget with real work still queued gets handled as additional
*internal* rounds within the same call, same live session, bounded by a second, independent cap
(distinct from the per-round budget) so a page that keeps generating genuinely new content faster
than any round can keep up with (infinite-scroll/live-chat-style) still terminates instead of
consuming the whole crawl:

```python
# Not: element_budget alone as the hard stop, then requeue-via-navigation if exceeded.
# Instead: element_budget * max_rounds as the real per-visit ceiling, all within one
# continuous session - only genuinely new content (per the consult-before-act check)
# keeps the loop going, so it still terminates on an ordinary page in one round.
max_total_interactions = element_budget * max_rounds_per_page
while frontier_has_unactioned_items and interactions_done < max_total_interactions:
    ...  # no re-navigation between "rounds" - same session throughout
```

A node that still isn't fully drained even after the combined ceiling should be left exactly as
persisted-but-incomplete (whatever "not finished" already means in your schema — e.g. `Pending`
status), never marked complete just because a pass happened. That's what makes the give-up
*honest*: a future run (or a human) can see precisely what's left, instead of the coverage gap
being indistinguishable from "this page genuinely has no more components."

## Making the frontier concurrent: `Queue.join()`, not a `while queue: ...` loop

**Symptom observed**: a real crawl of ~150 interactions took ~14 minutes wall-clock. Reading the
run's own debug log (per [debugging-agent-systems.md](debugging-agent-systems.md)'s "read the raw,
literal output" discipline) showed the crawl was never CPU- or network-bound - it was spending most
of its time in fixed settle-delay sleeps that exist for a real, documented reason (see
[crawl4ai-integration-pitfalls.md](crawl4ai-integration-pitfalls.md)'s hydration-wait entry), applied
once per interaction, entirely sequentially, one page at a time.

**Why it happens**: a fixed per-action sleep is real, necessary latency (the DOM genuinely hasn't
settled yet) - it can be *tuned* (a same-page click settles faster than a full page's first
hydration, so it deserves its own, shorter knob), but it can't be eliminated. The only way to stop N
pages' worth of fixed sleeps from summing linearly is to stop visiting them one at a time: run several
page-visits concurrently so their sleeps overlap instead of stacking.

**Fix pattern**: this is a classic producer-consumer termination problem in disguise - a single
`while frontier: url = frontier.popleft(); ...` loop can't safely become "run N of these at once"
just by wrapping it in a semaphore, because a worker that finds the frontier momentarily empty can't
tell "we're done" apart from "another in-flight worker is about to enqueue more" (a page's own links
get discovered *during* that page's visit, by a different worker than the one that will consume them).
`asyncio.Queue` already solves exactly this: its `unfinished_tasks` counter (incremented by every
`put`, decremented by every matching `task_done()`) is precisely the fact needed to disambiguate the
two cases, and `.join()` blocks until that counter hits zero - including tasks enqueued after `.join()`
was first called, not just the ones present at that moment.

```python
# N workers pulling from one shared queue, not N separate slices of a list -
# any worker can pick up a link any other worker just discovered.
async def crawl_site(self, start_url):
    self._enqueue(start_url)
    workers = [asyncio.create_task(self._worker()) for _ in range(concurrency)]
    await self._frontier.join()          # returns only once truly, fully drained
    for w in workers:
        w.cancel()                        # safe: join() guarantees every worker is idle here
    await asyncio.gather(*workers, return_exceptions=True)

async def _worker(self):
    while True:
        url = await self._frontier.get()
        try:
            ...  # visit url, _enqueue() any newly-discovered links (more put()s)
        finally:
            self._frontier.task_done()    # must run on every path, success or skip
```

Concurrency defaulting to 1 (one worker) reproduces the original fully-sequential behavior exactly,
including visit order - raising it is opt-in, not a rewrite of the single-worker case. One tradeoff to
document explicitly rather than silently accept: any shared counter-based cap (a `max_pages`-style
backstop) becomes a *soft* bound once concurrency > 1 - two workers can each pass a
"have we hit the cap" check before either increments the shared counter, since there's a real `await`
between the check and the increment. Same "documented, deliberate looseness" already established for
`element_budget`/`max_passes_per_page` elsewhere in this doc - not worth a lock for a backstop that
was never meant to be exact.

## Not every path onto the frontier goes through the dedup guard - a bypass built for one reason can let two workers claim the same item

**Symptom observed**: on a real crawl of `mapadeprofesionales.com` with `page_concurrency=10`, a
per-page debug artifact (crawl4ai's markdown snapshot of the page, saved to disk keyed by URL) for a
shared destination - `/login`, reached from many different pages' own "log in" links - got silently
overwritten mid-crawl, losing one session's content. Reading the raw debug log (per
[debugging-agent-systems.md](debugging-agent-systems.md)) showed the real shape of it: two *different*
session identifiers (`https://www.mapadeprofesionales.com/login` and
`https://www.mapadeprofesionales.com/`) with genuinely interleaved timestamps - not sequential, truly
concurrent.

**Why it happens**: the concurrent-frontier pattern above (`Queue.join()`, N workers) assumes exactly
one path adds items to the queue, gated by one dedup check. That stopped being true the moment a
*second* reason to enqueue something showed up: an interrupted-navigation follow-up (see
[crawl4ai-integration-pitfalls.md](crawl4ai-integration-pitfalls.md)'s "must stop that page's work
immediately" and "resolved URL, not original request" entries) has to re-queue the page it was
resuming *even though* that page is already marked as seen by the normal dedup guard - so it
deliberately bypasses that guard, by design, for a single-worker crawl that's a safe, narrow escape
hatch. Once a *second* worker can pop from the same queue, that bypass has no way to know whether some
completely unrelated page **also** redirected (at the navigation level - a plain HTTP/JS redirect
before any click, not one this crawl triggered) to the exact same destination and **also** independently
queued it through the same bypass. Both copies sit in the frontier; two idle workers each dequeue one;
both start visiting the identical page at once. This is worse than the debug-log symptom that exposed
it: a crawl4ai session is cached by its literal session-id string, so two coroutines were racing on the
literal *same* live browser tab, not just two independent tabs that happened to write the same file.

**Fix pattern**: a second guard, distinct from the "ever enqueued" dedup set - an **in-flight** set,
meaning "a worker is inside this item's visit *right now*" - consulted at dequeue time, before any
bypassed re-queue path gets a chance to matter:

```python
# _queued: "have we ever put this in the frontier" - permanent, checked by the normal enqueue path.
# _in_flight: "is a worker actively visiting this right now" - added just before the visit,
# discarded right after, checked by every worker BEFORE it starts a visit - including a visit
# reached via a dedup-bypassing re-queue, which is exactly the path _queued alone can't cover.
async def _worker(self):
    while True:
        item = await self._frontier.get()
        try:
            key = identity_of(item)
            if key in self._in_flight:
                continue  # someone else already owns finishing this - drop the duplicate, not the work
            self._in_flight.add(key)
            try:
                result = await self._visit(item)
            finally:
                self._in_flight.discard(key)
            ...  # bypassing re-queue path still exists, still needed - just no longer racy
        finally:
            self._frontier.task_done()
```

Dropping the duplicate loses no coverage: the worker that already owns the item will requeue it itself
if it's still not done, exactly as it would have anyway. The general lesson: **any time a queue gains a
second producer path that bypasses the first path's dedup on purpose, dequeue-time membership becomes
the only thing that can still catch a collision** - a bypass that was safe for a single consumer is not
automatically safe once a second one can race it.

## A same-page reveal chain needs the same churned-selector defense a cross-reload frontier already has

**Symptom observed**: a real crawl of austral.edu.ar got stuck interacting with a single interactive
widget (a book-page-viewer control) for 155+ consecutive interactions in one continuous session -
confirmed via a real debug log, where *every single* interaction event showed a clean, successful,
non-navigating result (no errors, no timeouts, nothing that looked broken) and yet the crawl never
progressed past it. This is a genuinely different shape from the two path-churn bugs above: no
navigation happened at all, and no dedup-bypass path was involved - the ordinary, entirely-intended
same-page-reveal mechanism (the one that lets a dropdown opening chain into exploring its own newly
revealed options) is what kept running.

**Why it happens**: a same-page widget can re-render its own DOM under a *fresh* selector path on every
interaction while its actual identity (tag/role/name/text) stays the same - the identical churned-id
pattern documented elsewhere in this doc for a page reload, just happening on every single same-page
interaction instead. The "append newly-revealed components to this pass's frontier" step only checked
*path*-based interacted status, with no content-identity fallback at all (unlike the navigation-specific
case, which by then already had one) - so every freshly-rendered instance of the identical widget looked
like genuinely new, never-before-seen work, and kept getting appended and clicked. Not literally infinite
(bounded by `element_budget * max_passes_per_page`, 2000 by default) but indistinguishable from stuck in
practice - each attempt costs a real network round trip, so 2000 of them against one uncooperative widget
consumes the time budget of an entire large crawl.

**Fix pattern**: track every component identity ever interacted with (success or failure) for a given
canonical page/state key - not just the ones proven to trigger navigation (a separate, narrower set kept
for that specific purpose) - and consult it everywhere components get added to a pass's frontier, not
just at the top of a fresh visit:

```python
interacted_identities[page_key].add(identity(component))  # recorded on every interaction, success or fail

# ... anywhere a "newly revealed" candidate is considered for the frontier:
if identity(candidate) in interacted_identities.get(page_key, set()):
    continue  # already handled once, under some other now-stale path
```

**The tradeoff, worth stating plainly rather than leaving implicit**: this is a broader, less airtight
rule than a "proven navigation trigger" fact - two components that happen to share the exact same
identity but are otherwise legitimately distinct (two generically-labelled "read more" cards linking to
different articles) would also collapse under this check, silently under-exploring the second one.
Accepted because the alternative - the crawl never terminating on a churning widget - is unambiguously
worse than an occasional missed near-duplicate-looking component; the same "decline redundant work"
calculus this doc's "Prefer decline over override" section already applies, scoped to a session-local
heuristic instead of a cross-run one.

**General, reusable lesson**: a "same-page reveal chains into further exploration" mechanism needs the
identical churned-selector defense a cross-reload/cross-page mechanism already has, the moment the thing
revealing content is itself capable of re-rendering under new ids on every interaction - which is close
to the *expected* case, not a rare edge case, for exactly the kind of rich, stateful same-page widget
(carousels, paginated viewers, virtualized lists) a same-page reveal chain exists to explore in the first
place. Don't assume a fix already shipped for "the same problem" at the page-reload granularity
automatically covers the same-page-interaction granularity too - each place components get added to a
frontier needs its own check.
