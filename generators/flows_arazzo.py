"""`flows.arazzo.json` - Arazzo 1.1.0 API call-sequence workflows, one per
observed trace, docs/adr/0014. Also renders the sequence-diagram section
`flows.md` folds `sequences` into (point 4).

**One workflow per trace, not per endpoint.** `user_flows.py`'s own
`FlowGraph` is deduplicated across every visit - exactly right for a UI
statechart, wrong for "a call sequence a user actually walked," which is
what Arazzo's `workflow` concept means. This module reuses
`generators.traces` (the same per-visit reconstruction `gherkin.py`'s own
scenarios are built from) instead.

**`operationId` cites `openapi.py`'s own real id** (ADR-0014 point 1) via
`generators.openapi.operation_id_for`, never re-derived independently -
Arazzo was built specifically to reference operations in a linked OpenAPI
`sourceDescriptions` document, so no extension is needed either.

**The `jsonpath`-typed `successCriteria` (ADR-0014 point 3) is always
absent, and that is a real, structural gap, not an oversight.** Appending
one is only correct when pragma's crawl evidence shows the same status
code returned with a body field whose value correlated with success or
failure - but `database/ladybug/network.py::get_inferred_requests` only
ever keeps a response example for a 2xx call (a failure's body describes
the error shape, not the happy path, so publishing it as *the* example
would misdescribe the API - the same reasoning `openapi.py`'s own
response examples already apply). Without a captured failure-body example
to compare against, there is nothing to correlate a field's value with,
so the baseline `simple` status-code criterion is every step's only one.
Capturing per-status response examples would be a new crawler capability,
not a change this document can make on its own.

Details: docs/dev/generators/flows_arazzo.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.documents import DocumentRequest
from core.interfaces import InferredRequest
from .ledger import flat_component_ledger
from .openapi import operation_id_for
from .traces import Trace, TraceStep, build_traces, render_sequence_diagram

ARAZZO_VERSION = "1.1.0"


def _is_observable(trace: Trace) -> bool:
    return any(step.navigated or step.requests for step in trace.steps)


def _observable_traces(request: DocumentRequest) -> List[Trace]:
    components = flat_component_ledger(request.graph_store)
    return [trace for trace in build_traces(components) if _is_observable(trace)]


def _step_operations(store: Any, trace: Trace) -> List[Tuple[TraceStep, InferredRequest]]:
    """`(step, inferred_request)` pairs in the trace's own order - one per
    step that genuinely `triggered_by` a real `InferredRequest`, the same
    `(page_url, path)` correlation `generators/gherkin_tags.py::correlate_trace`
    uses for `@REQ-<hash>`/`@EP-<hash>` tags, kept separate here (not
    imported) because the granularity differs: a workflow's steps must
    stay in trace order, one entry per step, where `correlate_trace`
    aggregates across a whole trace for a flat tag set.

    `loaded_by` is deliberately excluded - a page load firing a request is
    not "a step in a call sequence a user walked," which is what an
    Arazzo workflow models.
    Details: docs/dev/generators/flows_arazzo.md#_step_operations
    """
    inferred_requests = store.get_inferred_requests()
    pairs = []
    for step in trace.steps:
        if not step.requests:
            continue
        for inferred in inferred_requests:
            if (step.page_url, step.path) in inferred.triggered_by:
                pairs.append((step, inferred))
    return pairs


def _observed_status(step: TraceStep) -> Optional[int]:
    """The status this specific step's own fired request(s) actually
    observed - a failure with no captured status returns `None`, never a
    guessed code."""
    for request in step.requests:
        status = request.get("status")
        if isinstance(status, int):
            return status
    return None


def _success_criteria(step: TraceStep) -> List[Dict[str, Any]]:
    """The baseline `simple` status-code criterion (ADR-0014 point 3),
    from this step's own observation - omitted, not guessed, when no
    status was captured (a failed request with no response). The second,
    `jsonpath`-typed criterion the ADR describes is never appended; see
    the module docstring for why the evidence it requires doesn't exist
    in this crawl's capture model.
    Details: docs/dev/generators/flows_arazzo.md#_success_criteria
    """
    status = _observed_status(step)
    if status is None:
        return []
    return [{"condition": f"$statusCode == {status}"}]


def _arazzo_step(step_number: int, step: TraceStep, inferred: InferredRequest) -> Dict[str, Any]:
    arazzo_step: Dict[str, Any] = {
        "stepId": f"step{step_number}",
        "operationId": operation_id_for(inferred),
    }
    criteria = _success_criteria(step)
    if criteria:
        arazzo_step["successCriteria"] = criteria
    return arazzo_step


def _workflow_id(trace: Trace) -> str:
    return f"flow-{trace.visit_id}"


def _arazzo_workflow(trace: Trace, store: Any) -> Optional[Dict[str, Any]]:
    """One workflow per trace, or `None` when the trace fired nothing that
    correlates to a real operation - an empty `steps` array describes no
    call sequence at all, so the trace is excluded rather than emitted as
    a workflow with nothing in it.
    Details: docs/dev/generators/flows_arazzo.md#_arazzo_workflow
    """
    operations = _step_operations(store, trace)
    if not operations:
        return None
    return {
        "workflowId": _workflow_id(trace),
        "steps": [
            _arazzo_step(number, step, inferred)
            for number, (step, inferred) in enumerate(operations, 1)
        ],
    }


def build_arazzo_document(request: DocumentRequest) -> Dict[str, Any]:
    """`flows.arazzo.json` - one workflow per observed trace with at least
    one real operation correlation.
    Details: docs/dev/generators/flows_arazzo.md#build_arazzo_document
    """
    store = request.graph_store
    workflows = [
        workflow
        for trace in _observable_traces(request)
        if (workflow := _arazzo_workflow(trace, store)) is not None
    ]
    return {
        "arazzo": ARAZZO_VERSION,
        "info": {"title": f"{request.site} call sequences", "version": "1.0.0"},
        "sourceDescriptions": [{"name": "openapi", "url": "./openapi.yaml", "type": "openapi"}],
        "workflows": workflows,
    }


def _diagram_title(trace: Trace) -> str:
    """A deterministic title from the trace's own start/end - no model
    call. `flows.md` is a mechanically rendered view; the narrated titles
    `gherkin.py`'s scenarios carry belong to that document, not this one.
    """
    return f"{trace.start_page} -> {trace.end_page}" if trace.end_page != trace.start_page else trace.start_page


def render_flows_sequence_diagrams(request: DocumentRequest) -> str:
    """The "## Sequence Diagrams" section `flows.md` folds `sequences`
    into (ADR-0014 point 4) - one diagram per observed trace, the same
    set `build_arazzo_document` draws its workflows from, though a trace
    with no real operation correlation still gets a diagram here (it's
    still a real observed sequence, even if none of it maps to a citable
    OpenAPI operation).
    Details: docs/dev/generators/flows_arazzo.md#render_flows_sequence_diagrams
    """
    traces = _observable_traces(request)
    lines = ["## Sequence Diagrams", ""]
    if not traces:
        lines.append("No ordered interaction traces were recorded.")
        return "\n".join(lines) + "\n"

    lines += [
        "The same observations `flows.xstate.json`/`flows.arazzo.json` are built from, drawn. Not a "
        "second source of truth - a trace already *is* a sequence, so these cannot disagree with "
        "either source document.",
        "",
    ]
    for trace in traces:
        lines += [f"### {_diagram_title(trace)}", "", render_sequence_diagram(trace), ""]
    return "\n".join(lines)
