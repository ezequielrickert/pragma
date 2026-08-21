# `generators/flows_arazzo.py`

## module

Arazzo 1.1.0 API call-sequence workflows, one per observed trace
(docs/adr/0014). `user_flows.py`'s own `FlowGraph` is deduplicated across
every visit - right for a UI statechart, wrong for "a call sequence a
user actually walked," which is what an Arazzo `workflow` means, so this
reuses `generators.traces` (the same per-visit reconstruction
`gherkin.py`'s own scenarios are built from) instead of the flow graph.

Also renders the "## Sequence Diagrams" section `flows.md` folds
`sequences` into (point 4), since both need the identical set of
observed traces.

**The `jsonpath`-typed `successCriteria` (ADR-0014 point 3) is always
absent, on purpose.** Appending one needs a captured failure-response
body to correlate a field's value against, and
`database/ladybug/network.py::get_inferred_requests` only ever keeps a
response example from a 2xx call - a failure's body describes the error
shape, not the happy path, so pragma's crawl has never captured the
evidence this criterion would need. The baseline `simple` status-code
criterion is every step's only one until a new crawler capability
changes that.

## _step_operations

`(step, inferred_request)` pairs in the trace's own order. Deliberately
not built by calling `generators/gherkin_tags.py::correlate_trace` even
though the underlying `(page_url, path)` match against `triggered_by` is
identical: `correlate_trace` aggregates across a whole trace into a flat
tag set, and a workflow's steps need to stay in trace order, one entry
per step - a genuinely different shape, not the same one restated.

`loaded_by` is excluded on purpose: a page load firing a request is not
"a step in a call sequence a user walked."

## _observed_status

The status *this* step's own fired request(s) actually returned - not
the endpoint's aggregate `status_codes`, which could include a code a
different visit observed. Returns `None` rather than guessing when
nothing was captured (a failed request with no response).

## _success_criteria

The one real criterion this document can honestly emit: `$statusCode ==
<the status this step itself observed>`. Omitted entirely, not defaulted
to some plausible-sounding value, when `_observed_status` found nothing -
see the module docstring for why the second, `jsonpath`-typed criterion
never appears at all.

## _arazzo_workflow

`None` when a trace produced zero step/operation correlations - an empty
`steps` array would describe no call sequence at all, so the trace is
excluded from `flows.arazzo.json` entirely (it can still appear in the
sequence-diagram section, which doesn't require a citable operation).

## build_arazzo_document

`sourceDescriptions` points at the real `openapi.yaml` this pipeline
already generates - Arazzo was built specifically to reference operations
in a linked OpenAPI document, so `operationId` alone (via
`generators.openapi.operation_id_for`) is enough; no extension needed.

## _diagram_title

A deterministic `start -> end` title, not a narrated one. `flows.md` is a
mechanically rendered view (ADR-0009's own "never hand-authored in
parallel" discipline, applied here); the narrated titles `gherkin.py`'s
scenarios carry belong to that document, which is explicit about calling
a model for exactly one thing. This document calls no model at all.

## render_flows_sequence_diagrams

The same observed-trace set `build_arazzo_document` draws its workflows
from, but every trace gets a diagram here - even one with zero operation
correlations is still a real observed sequence, just not one that maps to
a citable OpenAPI operation.
