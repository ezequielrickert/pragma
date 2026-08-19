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

`[]` for a site serving its CSS cross-origin: `cssRules` throws for those
stylesheets and there is no way around it. The design-token document says so
rather than presenting an empty list as "this site declares no hover styles".
