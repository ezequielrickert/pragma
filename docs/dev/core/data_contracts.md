# `src/core/data_contracts.py`

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
