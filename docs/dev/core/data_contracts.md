# `core/data_contracts.py`

## module

Split out of `interfaces.py` (2026-08-12) once that file crossed this
project's 500-line file-size-audit watch threshold - `PageState`/
`ComponentFacts`/`ComponentFamily`/`InferredRequest` are plain data
(dataclasses, no behavior), as opposed to `Agent`/`GraphStore` (real
interfaces, abstract base classes with methods to implement), so they're
the natural seam to split along.

`interfaces.py` re-imports and re-exports every name from here (`from
.data_contracts import PageState, ComponentFacts, ...`) - every existing
`from ..core.interfaces import ComponentFacts` import site across the
codebase keeps working unchanged; nothing outside these two files needed
to change when the split happened. See `interfaces.md#module` for the
other half of this split.

Field-by-field documentation for each dataclass lives on the class itself
(docstrings), not duplicated here - `PageState` in its own class
docstring plus per-field comments, `ComponentFacts` referencing
`interfaces.md#componentfacts` (kept as the historical anchor name for
that one), `ComponentFamily`/`InferredRequest` with a full `Fields:`
section each.

## VisitStep

Where one interaction sits in the sequence of a single page visit.

A BDD scenario is a *sequence*, and until this existed the graph recorded
facts per component with no ordering between them: a stepper's `+ + -` and
`- + +` were indistinguishable, and a control clicked twice pooled its
network responses with nothing saying which belonged to which.

`visit_id` says which pass an interaction belonged to; `seq` orders it
within that pass. The same `VisitStep` instance is handed to both
`record_interaction` and `record_component_network` for one interaction,
which is what pairs a request with the click that fired it after the store
flattens every batch into one list.

Mutable, and created per `PageVisitor.visit()` call rather than held on
the visitor. One `PageVisitor` is shared across concurrent workers, so a
counter on the instance would interleave two pages' steps into a single
nonsense sequence - a bug that would only appear under `page_concurrency
> 1` and would look like corrupt data rather than a race.

`take()` returns a frozen snapshot rather than the live object, so a
caller holding a step cannot see it advance underneath them.

## pagestatepseudo_styles

The declared `:hover`/`:focus` styles per control, as
`[{"path", "states"}]` - `extract_pseudo_styles.js`'s own output shape.

**Unlike geometry, this does not depend on the viewport.** It is read from
`document.styleSheets`, so the crawl's 800x600 window and blocked images do not
affect it, which is why it rides along in the ordinary discovery pass instead of
needing the measurement pass it was originally written for.

## pagestatearia_snapshot_yaml

Playwright `ariaSnapshot()` YAML and CDP `Accessibility.getFullAXTree`
JSON, captured once per discovery (docs/adr/0003) - the raw text pair
`generators/aria_tree.py` parses into `tree.aria.yaml`/`tree.axtree.json`.
Both `""` when capture failed
(`spiders/content/accessibility_snapshot.py` degrades rather than raising)
or the page predates this instrumentation - never a placeholder value, so
`database/ladybug/accessibility_snapshot.py::record_accessibility_snapshot`
can tell "nothing captured" from "captured an empty tree" and skip the
write for the former.

`[]` for a site serving its CSS cross-origin: `cssRules` throws for those
stylesheets and there is no way around it. The design-token document says so
rather than presenting an empty list as "this site declares no hover styles".

## pagestateblocked_mutations

Mutating requests (`POST`/`PUT`/`PATCH`/`DELETE`, or a `GET` the mutation
heuristic flagged) the mode-gate handler
(`spiders/browser/crawl4ai_crawler/hooks.py`) intercepted and fulfilled
synthetically instead of letting reach the network, in `immutable` mode -
`[{"method", "url"}]`. `[]` in `stateful` mode, or for a backend without a
mode-gate at all.

`PageVisitor.visit` reads this the same call it reads `network_requests`
from, turning it into the `blocked`/`blocked_reason` pair
`sink.record_interaction` writes onto the `Interaction` node - a request
this list carries never produced a `Request`/`TRIGGERED` pair of its own,
since it never reached the network. Issue #62.
