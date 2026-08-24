"""Flow derivation: one `SemanticFlow` per `Trace`, per 'Define Flow
semantics and derivation algorithm' (issue #189, part of the same map as
`screens.py`). Pure and deterministic, no model call - the derivation
research (issue #186) found `name`/`goal` fully templatable from data
already on the `Trace`, so unlike `Screen` this tier needs no separate
narration module.

Written for every trace, including one whose terminal step neither
navigated nor fired a request - `flows_arazzo.py::_is_observable`
excludes those because Arazzo has nothing executable to say about them;
`Flow` is describing what happened, where a dead-end path is itself
useful to see.

Details: docs/dev/generators/flows.md#module
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.interfaces import InferredRequest, SemanticFlow
from generators.openapi import operation_id_for
from generators.traces import Trace, TraceStep, build_traces
from generators.user_flows import request_outcome
from utils.urls import route_shape

_WORD_RE = re.compile(r"[A-Z][a-z]*|[a-z]+")

# Closed goal-verb taxonomy (issue #196): overrides tier-1's raw CRUD-verb
# phrase whenever the terminal request's `endpoint` case-insensitively
# contains one of a phrase's keywords, regardless of HTTP method. First
# match wins, in this priority order - local to this module, deliberately
# never shared with `generators/openapi.py`'s `operation_id_for`/`_summary`
# (changing those would change already-emitted `openapi.yaml` content, a
# separate decision).
# Details: docs/dev/generators/flows.md#_GOAL_VERB_TAXONOMY
_GOAL_VERB_TAXONOMY: Tuple[Tuple[Tuple[str, ...], str], ...] = (
    (("logout", "signout"), "Log out"),
    (("checkout", "pay"), "Purchase"),
    (("signup", "register"), "Sign up"),
    (("login", "signin"), "Log in"),
    (("search",), "Search"),
    (("delete", "remove"), "Delete"),
)


def _goal_verb_override(endpoint: str) -> Optional[str]:
    """The taxonomy phrase for `endpoint`, or `None` if no keyword
    matches - first row in `_GOAL_VERB_TAXONOMY` order wins.
    Details: docs/dev/generators/flows.md#_goal_verb_override
    """
    lowered = endpoint.lower()
    for keywords, phrase in _GOAL_VERB_TAXONOMY:
        if any(keyword in lowered for keyword in keywords):
            return phrase
    return None


def _terminal_step(trace: Trace) -> Optional[TraceStep]:
    """The trace's last step, or `None` for an empty trace - the one
    place that decision is made, shared by every tier below that reads
    off "how did this journey end".
    Details: docs/dev/generators/flows.md#_terminal_step
    """
    return trace.steps[-1] if trace.steps else None


def _humanized(operation_id: str) -> str:
    """`"createOrder"` -> `"Create order"` - `operation_id_for`'s own
    camelCase, split into words and re-capitalized as a phrase rather
    than an identifier. No new vocabulary: a formatting transform over
    the exact string `openapi.yaml` already carries.
    Details: docs/dev/generators/flows.md#_humanized
    """
    words = _WORD_RE.findall(operation_id)
    if not words:
        return operation_id
    return " ".join([words[0].capitalize(), *(word.lower() for word in words[1:])])


def _terminal_request(trace: Trace, inferred_requests: Sequence[InferredRequest]) -> Optional[InferredRequest]:
    """The `InferredRequest` behind the trace's own terminal step, if its
    firing component correlates to one - the same `(page_url, path) in
    triggered_by` correlation `flows_arazzo.py::_step_operations` uses,
    narrowed to one step since a Flow's name cites where the journey
    ended, not every call it made along the way. Sorted by
    `(method, endpoint)` when more than one candidate correlates, so the
    choice is reproducible rather than dependent on read order.
    Details: docs/dev/generators/flows.md#_terminal_request
    """
    terminal = _terminal_step(trace)
    if terminal is None or not terminal.requests:
        return None
    candidates = [
        inferred for inferred in inferred_requests
        if (terminal.page_url, terminal.path) in inferred.triggered_by
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda inferred: (inferred.method, inferred.endpoint))[0]


def _name_and_goal(trace: Trace, inferred_requests: Sequence[InferredRequest]) -> Tuple[str, str]:
    """The `(name, goal)` cascade: terminal-endpoint CRUD phrase, else
    terminal `route_shape`, else the generic step-count fallback - first
    tier with something to say wins, per issue #189's resolution.
    Details: docs/dev/generators/flows.md#_name_and_goal
    """
    terminal_request = _terminal_request(trace, inferred_requests)
    if terminal_request is not None:
        override = _goal_verb_override(terminal_request.endpoint)
        name = override if override is not None else _humanized(operation_id_for(terminal_request))
        goal = f"{name} ({terminal_request.method} {terminal_request.endpoint})"
        return name, goal

    # `Trace.end_page` always resolves to something (it falls back to
    # `start_page` itself when nothing navigated), so the tier gate has
    # to ask the terminal step directly rather than trust that property's
    # own truthiness - see this ticket's own definition of "non-observable"
    # (the terminal step neither navigated nor fired a request), which
    # this cascade's three tiers mirror one-for-one.
    terminal = _terminal_step(trace)
    if terminal is not None and terminal.navigated:
        pattern = route_shape(terminal.resulting_url)
        return pattern, f"Reach {pattern}."

    fallback = f"{len(trace.steps)}-step flow from {trace.start_page}"
    return fallback, fallback


def _outcome(trace: Trace) -> str:
    """The terminal step's own fired-request outcome, bucketed via
    `generators/user_flows.py::request_outcome` - no separate taxonomy.
    Details: docs/dev/generators/flows.md#_outcome
    """
    terminal = _terminal_step(trace)
    requests = terminal.requests if terminal is not None else ()
    return request_outcome(list(requests))[0]


def _build_flow(trace: Trace, inferred_requests: Sequence[InferredRequest]) -> SemanticFlow:
    name, goal = _name_and_goal(trace, inferred_requests)
    return SemanticFlow(
        visit_id=trace.visit_id,
        name=name,
        goal=goal,
        step_count=len(trace.steps),
        outcome=_outcome(trace),
        # Each step's real `step_seq` - what `record_flows` matches back
        # against `Interaction {visit_id, step_seq}` to write `STEP_OF.seq`
        # and the provenance edge. Not a recomputed 0-based position: a
        # visit's stamped sequence can have gaps (an unstamped interaction
        # filtered out upstream), so only the real value round-trips.
        derived_from=tuple(step.step_seq for step in trace.steps),
    )


def build_flows(components: Sequence[Dict[str, Any]], inferred_requests: Sequence[InferredRequest]) -> List[SemanticFlow]:
    """One `SemanticFlow` per trace the crawl walked.

    Args:
        components: `ledger.flat_component_ledger` output - the same
            argument `build_traces` itself takes.
        inferred_requests: `graph_store.get_inferred_requests()` - the
            terminal-endpoint naming tier's only data source.

    Returns:
        One `SemanticFlow` per `Trace` (`build_traces`'s own ordering:
        longest first, then `visit_id`), including a trace whose terminal
        step neither navigated nor fired a request - see this module's
        own docstring for why that diverges from `flows_arazzo.py`.
    Details: docs/dev/generators/flows.md#build_flows
    """
    return [_build_flow(trace, inferred_requests) for trace in build_traces(components)]
