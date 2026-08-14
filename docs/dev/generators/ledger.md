# `generators/ledger.py`

## module

The single place that reshapes `GraphStore.get_component_ledger`'s nested
`{page_url: {path: record}}` into the flat `[{page_url, path, ...}]` list
every whole-site pass consumes.

**Why the two shapes both exist, rather than the store returning one.**
The nesting is the right shape for `GraphPRDSynthesizer`: it narrates one
page at a time, so "this page's components" is exactly the lookup it
wants. It is the wrong shape for anything reasoning across the whole site
at once - `build_component_families` clusters look-alike components
wherever they live, and `build_inferred_requests` groups requests by
endpoint regardless of which page fired them. Neither cares which page a
component came from beyond keeping it as an identity field, so both start
by throwing the nesting away.

**What this replaced.** Before this module, `Engine._apply_component_
families` and `Engine._apply_request_graph` each carried their own
byte-identical five-line copy of the flattening comprehension, and every
document generator planned in `research/plan-generacion-de-documentos.md`
would have added another. Two copies is a coincidence; the third is a
pattern, and the pattern belongs in one function.

## flat_component_ledger

Reads and flattens in one call rather than taking an already-read ledger
dict, because the duplication being removed was the *read plus* the
flatten, not the flatten alone - every call site did both, back to back.

Deliberately does **not** sort. `build_component_families` and
`build_inferred_requests` each already sort by their own key (class
similarity buckets, `(method, endpoint, query_params)` respectively), so
sorting here would be work thrown away twice over, and picking one order
for every future caller would be guessing on their behalf. Callers that
need determinism sort what they need, when they need it - which is what
both current callers already do.
