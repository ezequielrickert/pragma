"""Traceability tag resolution for `generators/gherkin.py` (docs/adr/0013):
correlating one trace to `requirements.py`'s extraction rules and to the
graph's own module/screen ids. `gherkin.py` stays the pure trace-shape
renderer (a `Trace` in, Gherkin/Mermaid text out, no store needed);
everything here needs a store or `core.graph_metrics`, the one real
boundary between the two modules (and the reason this is a separate file
rather than the `usability`/`usability_act` shape: no circular import
risk to dodge here, just a genuine store-dependent/pure split).

`@REQ-<hash>` and `@confidence:observed` are required on every scenario
`GherkinDocument` writes - a trace whose steps correlate to none of
`requirements.py`'s own extraction rules isn't written as a scenario at
all (excluded, counted, reported by the caller), rather than carrying a
missing or fabricated required tag. `@EP-<hash>`/`@MOD-<slug|hash>`/
`@SCR-<hash>` are optional, added wherever the trace's own steps or
screens resolve to one.

Details: docs/dev/generators/gherkin_tags.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Set, Tuple

from core.documents import DocumentRequest
from core.graph_metrics import build_screen_graph, compute_graph_metrics
from utils.short_hash import short_hash
from utils.urls import route_shape
from .requirements import requirement_id
from .traces import Trace


def _endpoint_tag_id(target: str) -> str:
    """`EP-<hash>` (ADR-0013 point 1) - a deterministic hash of the graph's
    own `Endpoint` composite key (`database/ladybug/ids.py::endpoint_id`,
    `"METHOD host/path_pattern"`), which `target` (`requirements.py`'s own
    `f"{method} {endpoint}"` string) already equals exactly.
    Details: docs/dev/generators/gherkin_tags.md#_endpoint_tag_id
    """
    return f"EP-{short_hash(target)}"


def _screen_tag_id(page_url: str) -> str:
    return f"SCR-{short_hash(page_url)}"


def trace_screens(trace: Trace) -> Tuple[str, ...]:
    """Every distinct screen this trace touches, in the order visited -
    the start page, plus every page a navigating step actually landed on.
    Details: docs/dev/generators/gherkin_tags.md#trace_screens
    """
    screens = [trace.start_page]
    for step in trace.steps:
        if step.navigated and step.resulting_url not in screens:
            screens.append(step.resulting_url)
    return tuple(screens)


def screen_tags(trace: Trace) -> Tuple[str, ...]:
    return tuple(_screen_tag_id(page_url) for page_url in trace_screens(trace))


@dataclass(frozen=True)
class TraceCorrelations:
    """Every real correlation one trace's steps have to
    `requirements.py`'s own extraction rules - computed once per trace and
    reused for both `@REQ-<hash>` and `@EP-<hash>` tags, rather than two
    passes independently walking the same `get_inferred_requests()` data.
    Details: docs/dev/generators/gherkin_tags.md#tracecorrelations
    """

    requirement_ids: Tuple[str, ...]
    endpoint_ids: Tuple[str, ...]


def correlate_trace(store: Any, trace: Trace) -> TraceCorrelations:
    """Recomputes exactly what `_event_driven_requirements`/
    `_ubiquitous_requirements`/`_unwanted_behavior_requirements`
    (`generators/requirements.py`) would derive from the same
    `InferredRequest`s, restricted to the ones this trace's own steps
    genuinely triggered or loaded - `requirement_id` then guarantees the
    identical `REQ-<hash>` `requirements.json` itself would emit for that
    observation, never a second, independently-derived id.

    `unwanted_behavior` only applies to an endpoint this trace already
    `touched` via `triggered_by`/`loaded_by` - a failure on an endpoint
    this trace never called is not this trace's own requirement.
    Details: docs/dev/generators/gherkin_tags.md#correlate_trace
    """
    step_positions = {(step.page_url, step.path) for step in trace.steps}
    visited_pages = set(trace_screens(trace))
    requirement_ids: Set[str] = set()
    endpoint_ids: Set[str] = set()

    for inferred in store.get_inferred_requests():
        target = f"{inferred.method} {inferred.endpoint}"
        touched = False
        for page_url, path in inferred.triggered_by:
            if (page_url, path) in step_positions:
                trigger = f"the user interacts with {path} on {page_url}"
                requirement_ids.add(requirement_id("event_driven", trigger, target))
                touched = True
        for page_url in inferred.loaded_by:
            if page_url in visited_pages:
                trigger = f"{page_url} is displayed"
                requirement_ids.add(requirement_id("ubiquitous", trigger, target))
                touched = True
        if not touched:
            continue
        endpoint_ids.add(_endpoint_tag_id(target))
        if any(code >= 400 for code in inferred.status_codes):
            trigger = f"the call to {target} fails"
            requirement_ids.add(requirement_id("unwanted_behavior", trigger, target))

    return TraceCorrelations(requirement_ids=tuple(sorted(requirement_ids)), endpoint_ids=tuple(sorted(endpoint_ids)))


def screen_module_ids(request: DocumentRequest) -> Dict[str, str]:
    """`{SCR-<hash>: MOD-<slug|hash>}` - the same hybrid path-prefix/Leiden
    module derivation `prd.md`/`architecture.calm.json` use (ADR-0007),
    the literal `MOD-<x>` tag id (ADR-0013 point 2) rather than
    `requirements.py`'s own human-readable `module_label`.
    Details: docs/dev/generators/gherkin_tags.md#screen_module_ids
    """
    store = request.graph_store
    root = route_shape(request.settings.get("target", "")) or None
    metrics = compute_graph_metrics(build_screen_graph(store, store.get_edges()), root=root)
    return {_screen_tag_id(module.node_id): module.module_id for module in metrics.node_modules}


def module_tags(module_ids_by_screen: Dict[str, str], trace: Trace) -> Tuple[str, ...]:
    return tuple(sorted({
        module_ids_by_screen[screen_tag]
        for page_url in trace_screens(trace)
        if (screen_tag := _screen_tag_id(page_url)) in module_ids_by_screen
    }))


def tag_line(correlations: TraceCorrelations, module_ids: Tuple[str, ...], screen_ids: Tuple[str, ...]) -> str:
    """`@REQ-<hash>` + `@confidence:observed` first (both required,
    ADR-0013 point 3) - `confidence` is always `"observed"` here because
    `event_driven`/`ubiquitous`/`unwanted_behavior` are the only EARS
    patterns a trace step can correlate to, and `requirements.py` never
    emits any of the three at any confidence but `"observed"`. Then
    `@EP-<hash>`/`@MOD-<x>`/`@SCR-<hash>`, all optional.
    Details: docs/dev/generators/gherkin_tags.md#tag_line
    """
    tags = [f"@{req_id}" for req_id in correlations.requirement_ids] + ["@confidence:observed"]
    tags += [f"@{ep_id}" for ep_id in correlations.endpoint_ids]
    tags += [f"@{mod_id}" for mod_id in module_ids]
    tags += [f"@{scr_id}" for scr_id in screen_ids]
    return "  " + " ".join(tags)
