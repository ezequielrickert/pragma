# Research: root-causing the "Neurología ×4" same-page multi-path collapse (#167)

Child of map #164.

## Question

In `data/sites/mapadeprofesionales.com.lbdb`, canonical `Component`
`component:4bf422200c40fb38358bb8989d3a8bef68a5a80c` (a "Neurología" filter
button) carries 4 `HAS_COMPONENT` edges, all from the same `Page` node
(`mapadeprofesionales.com`, not a `#state:` variant), at 4 distinct DOM
paths. Is the current exact-reuse collapse correct behavior that just needs
better visibility, or is it a real discovery/matching bug?

## Confirmed forensics (starting point, not redone here)

4 `HAS_COMPONENT` edges from Page `mapadeprofesionales.com` to the
Neurología `Component`, all nested inside the sidebar `<aside>`.

## Step 1 — the actual 4 DOM paths

Queried directly against the `.lbdb` dataset with the `ladybug` binding:

```
MATCH (p:Page)-[e:HAS_COMPONENT]->(c:Component {id: "component:4bf422200c40fb38358bb8989d3a8bef68a5a80c"})
RETURN p.url, e.path
```

```
1. body > div#root > div > main > div > div:nth-of-type(3) > div > div > div:nth-of-type(1) > div > aside > div > div:nth-of-type(5) > div:nth-of-type(2) > div:nth-of-type(4) > button
2. body > div#root > div > main > div > div:nth-of-type(3) > div > div > div:nth-of-type(1) > div > aside > div > div:nth-of-type(3) > div:nth-of-type(2) > button:nth-of-type(2)
3. body > div#root > div > main > div > div:nth-of-type(3) > div > div > div:nth-of-type(1) > div > aside > div > div:nth-of-type(2) > div:nth-of-type(2) > div > div:nth-of-type(2) > button
4. body > div#root > div > main > div > div:nth-of-type(3) > div > div > div:nth-of-type(1) > div > aside > div > div:nth-of-type(3) > div:nth-of-type(2) > button:nth-of-type(1)
```

These are **not** four occurrences of one repeating template at a fixed
container (a responsive duplicate, a repeating filter group, a "selected
chip" echo) — the paths diverge at completely different `<aside>` child
branches (`div:nth-of-type(5)`, `div:nth-of-type(3)` twice, `div:nth-of-type(2)`).
A genuine "rendered N times in one DOM snapshot" control sits in N
structurally-parallel slots (same shape, different index at one level); this
does not have that shape.

The smoking gun came from checking a second component in the same
container, `Component f894004c... ("Filtrar por favoritos")`, which also
has exactly 4 edges from the same Page:

```
1. ...aside > div > div:nth-of-type(5) > div:nth-of-type(2) > div:nth-of-type(4) > button   <- IDENTICAL to Neurología path 1
2. ...aside > div > div:nth-of-type(3) > div:nth-of-type(2) > button:nth-of-type(2)          <- IDENTICAL to Neurología path 2
3. ...aside > div > div:nth-of-type(2) > div:nth-of-type(2) > div > div:nth-of-type(2) > button <- IDENTICAL to Neurología path 3
4. ...aside > div > div:nth-of-type(1) > div > button:nth-of-type(1)                          <- differs
```

Two components with **different text** ("Filtrar por favoritos" vs.
"Neurología") sharing 3 of 4 identical CSS paths is impossible within a
single DOM snapshot — `discover_components.js`'s path builder (`gp()`) is
memoized per-element per-call and disambiguates siblings by live
`nth-of-type` position, so two different elements can never resolve to the
same string in one call. The only way two different buttons end up
"at" the same path string is if those path strings were computed in
**separate discovery passes taken at different moments**, when the
`<aside>` subtree's sibling counts/order had shifted enough that the same
`nth-of-type` string now names a different slot.

## Step 2 — how discovery actually runs, and the mechanism that explains this

`spiders/content/js/discover_components.js`'s `gp()` builds each element's
path from live sibling position (`nth-of-type`) at the moment it runs; it
is only valid within that one call. The codebase already knows this:
`spiders/orchestration/page_visitor/visitor.py`'s `interact()` docstring
says outright "a component's own path/selector churns across separate
`discover_page()` reloads."

`discover_components.js` (`page_extraction.py::run_extraction`) is *not*
run once per page. `PageVisitor._drain_interaction_frontier`
(`spiders/orchestration/page_visitor/visitor.py`) re-runs it after every
single click/fill during the page's interact sweep. When a click changes
the DOM without navigating and the before/after component-set overlap
stays above `state_transition_overlap_threshold`, the outcome is classified
as "same-URL DOM change" (`visitor.py` line ~468) and routed to
`outcomes.py::handle_same_page_reveal`, which calls
`self.sink.record_inventory(page_key, new_state.components, new_state.links)`
— i.e. it re-persists **every** component in the fresh snapshot under the
**same** `page_key`, `HAS_COMPONENT` included.

`database/ladybug/component.py::record_component` `MERGE`s the edge on
`{path: $path}` — a distinct path always produces a distinct edge, even
onto the same canonical `Component` id (canonical identity there is
content-hash based — `tag`/`text`/`role`/`css_class`/etc. — and
deliberately excludes `path`, per that module's own docstring). So: every
time the sidebar's structure shifts slightly between two same-page-reveal
snapshots (an accordion group toggling, a list re-filtering, an insurer
selection reordering something), any component whose `nth-of-type` chain
crosses that shift gets a fresh path string and a fresh `HAS_COMPONENT`
edge — even though it is the same physical element as before.

**This explains the shared paths between two different buttons directly**:
Neurología and Favoritos are not colliding within one snapshot; different
physical elements occupied the same `nth-of-type` slot at different points
across the visit's sequence of same-page-reveal snapshots, and each
snapshot's full write left its own edge behind.

### The reused-click confirmation

The Neurología `Component` row itself carries `interacted = true`,
`interaction_count = 4`. Querying its `Interaction` nodes:

```
MATCH (c:Component {id: "component:4bf422200c40fb38358bb8989d3a8bef68a5a80c"})-[:PERFORMED]->(i:Interaction)
RETURN i.action, i.visit_id, i.step_seq ORDER BY i.step_seq
```

```
['click', 'e4a3dce34276', 7]
['click', 'e4a3dce34276', 8]
['click', 'e4a3dce34276', 9]
['click', 'e4a3dce34276', 14]
```

Same `visit_id` — **one single page visit clicked the same canonical
Neurología button four separate times.** This is a direct violation of
"interact-once" (issue #140/#135's stated design: a canonical component is
interacted with "at most once, ever, per run").

Tracing why the dedup missed it: the interact-once machinery has two
identity layers.

1. `analysis/exact_reuse_index.py::ExactReuseIndex` — built once at run
   start from a *persisted* ledger snapshot (`generators/ledger.py::
   flat_component_ledger`), and only tracks a component already known
   at 2+ locations *before* this run started (`len(locations) < 2:
   continue`). It cannot see reveals that happen live, mid-pass, on a page
   being visited for the first time — nothing has been persisted yet for
   those.
2. `spiders/orchestration/page_visitor/frontier.py::Frontier` —
   the in-process, per-visit guard meant to cover exactly that gap:
   `is_excluded()`/`mark_interacted_identity()` track
   `spiders/content/component_matching.py::component_identity()`, a tuple
   of `(tag, role, name, form, text)`, and `handle_same_page_reveal`'s
   append loop (`outcomes.py` line ~181) does call `is_excluded()` before
   re-adding a "revealed" candidate to the frontier.

The bug is in what `component_identity()` hashes on. Its `form` field is
populated by `discover_components.js` as
`el.closest('form') ? gp(el.closest('form')) : ''` — **also an
`nth-of-type`-derived path string**, subject to exactly the same
instability documented above. `component_identity()`'s own docstring
promises identity "stable across a DOM remount that reassigns ids," but
the `form` field breaks that promise: if the ancestor `<form>`'s own
computed path drifts between two same-page-reveal snapshots (plausible
here — Neurología's button sits inside a specialty search/filter form),
`component_identity()` computes a *different* tuple for the exact same
physical button across snapshots, `is_excluded()` fails to recognize it as
already-interacted, and the frontier re-adds and re-clicks it.

By contrast, the persisted graph-level identity
(`database/ladybug/ids.py::component_content_id`, via
`DESCRIPTIVE_COMPONENT_FIELDS` in `database/ladybug/schema.py`) never
included `form` at all — so all 4 discoveries correctly collapsed onto one
canonical `Component` row in the graph, even though the live in-process
dedup that should have prevented 3 of the 4 clicks from happening in the
first place did not.

"Filtrar por favoritos" is consistent with this: its `interaction_count`
is `1` (properly deduped after its first click at `step_seq 2`) even though
it still accumulated 4 `HAS_COMPONENT` edges — because `record_inventory`
re-persists the *entire* fresh component snapshot on every same-page
reveal regardless of interaction status, so a stable click-dedup does not
by itself prevent duplicate edges once paths drift.

## Step 3 — is this isolated to Neurología, or systemic across the sidebar?

Counted `HAS_COMPONENT` edges from the same Page node for every `<button>`
in the `<aside>` sidebar:

```
Filtrar por favoritos   4
Neurología               4
Ej: Argentina            1
T. ocupacional           1
Medifé                   1
OSDE                     1
Psiquiatría              1
Galeno                   1
Hospital Austral         1
OMINT                    1
Coaching                 1
Buscar                   1
Swiss Medical            1
Filtrar por verificados  1
Buscar obra social...    1
Psicopedagogía           1
Psicología               1
IOMA                     1
Medicus                  1
Otros                    1
Limpiar                  1
Cerrar                   1
```

Only 2 of 22 sidebar filter controls show the multiplication — every other
specialty option (Psicología, Psiquiatría, Psicopedagogía, T. ocupacional,
Coaching, ...) and every insurer chip appears exactly once from this Page
node. If the site genuinely re-rendered the whole specialty list N times
per page load (a responsive duplicate, a repeated filter group), every
specialty button in that list would show the same multiplicity — they
don't. This rules out "systemic, expected" and confirms the pattern is
tied to specific components that happened to get interacted with in this
particular visit's sequence (both Favoritos and Neurología are early
frontier items — clicked at step 2 and step 7 respectively — plausibly
inside/near the same search-form ancestor whose own path churns).

Step 4 (live browser check) was skipped — the code-level and
interaction-log evidence above (same `visit_id`, four sequential
`step_seq` clicks, identical paths shared across two differently-labeled
buttons) is already conclusive without it.

## Step 5 — conclusion

**This is a real bug, not a visibility gap.** The current model is not
"correctly" representing 4 genuine physical instances of one control on
one page load. It is:

1. A functional **interact-once regression**: the same physical Neurología
   button was clicked 4 times in one visit (`step_seq` 7, 8, 9, 14, same
   `visit_id`), when the design intent (#135/#140) is at most once.
2. A **graph-write side effect** of the same underlying instability: every
   same-page reveal re-persists the whole component snapshot
   (`handle_same_page_reveal` → `record_inventory`), and because
   `HAS_COMPONENT` is `MERGE`d on the raw `path` string
   (`database/ladybug/component.py`), a path that drifts between
   snapshots — because `nth-of-type`-based paths are not stable identifiers
   across time within one page visit, something the codebase already
   documents elsewhere but doesn't defend against here — produces spurious
   extra edges on the same canonical component from the same page.

### Needed follow-up (not created as an issue, no code changed)

- **Primary fix**: `spiders/content/component_matching.py::component_identity()`
  (lines ~21–31) should stop hashing the `form` field as currently
  computed. Today it's `gp(el.closest('form'))` (`discover_components.js`),
  an `nth-of-type`-derived path string that inherits the exact instability
  `component_identity()`'s own docstring claims to be immune to. Either
  drop `form` from the identity tuple entirely, or replace it with
  something not DOM-position-derived (e.g. the form's own semantic
  identity — its `name`/`id`/aria-label — falling back to `''` rather than
  a path when none of those exist). This is what should have made
  `spiders/orchestration/page_visitor/frontier.py::Frontier.is_excluded()`
  correctly recognize Neurología as already-interacted at `step_seq 8`.
- **Secondary, lower priority**: even with the above fixed,
  `outcomes.py::handle_same_page_reveal`'s unconditional
  `record_inventory(page_key, new_state.components, ...)` on every reveal
  will still write a fresh `HAS_COMPONENT` edge for any component whose
  `path` happens to drift between two same-page snapshots, independent of
  whether it was clicked. Worth a separate design pass on whether
  `HAS_COMPONENT`'s `path` `MERGE` key should tolerate this (e.g. some
  notion of "this component's edge on this page already exists, only
  update it" rather than "unique per literal path string"), since the
  store currently has no way to tell "a second, truly simultaneous
  physical instance" apart from "the same instance re-observed later with
  a drifted selector."

## Evidence appendix

- `.venv/bin/python3` + `ladybug` binding, queried directly against
  `data/sites/mapadeprofesionales.com.lbdb` (read-only).
- Schema notes used: `Component` node fields via
  `CALL TABLE_INFO("Component")`; `HAS_COMPONENT` edge carries `path`
  (and geometry) per `database/ladybug/component.py`; `Interaction` node
  fields (`action`, `source_path`, `visit_id`, `step_seq`) via
  `CALL TABLE_INFO("Interaction")`.
- Code read: `spiders/content/js/discover_components.js`,
  `spiders/content/page_extraction.py`,
  `spiders/browser/crawl4ai_crawler/hooks.py`,
  `spiders/orchestration/page_visitor/visitor.py`,
  `spiders/orchestration/page_visitor/outcomes.py`,
  `spiders/orchestration/page_visitor/frontier.py`,
  `spiders/content/component_matching.py`,
  `database/ladybug/component.py`,
  `database/ladybug/schema.py`,
  `analysis/exact_reuse_index.py`.
