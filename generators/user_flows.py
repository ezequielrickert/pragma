"""D6: the finite-state machine a crawl walked - which screens exist, what
moves between them, and which moves fail.

Needs no new capture. Every transition is a `NAVIGATED_TO` edge the crawl
already wrote; the endpoint and status on it come from the network
requests already sitting on the component that triggered it.

The error branches are what make this worth reading. A diagram of the
happy path restates the navigation menu; one that shows the checkout
POST answering 422 and landing you back on the form describes how the
application actually behaves.

Details: docs/dev/generators/user_flows.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.urls import route_shape
from .ledger import flat_component_ledger
from .traces import requests_for

OK = "ok"
ERROR = "error"
UNKNOWN = "unknown"
# One control that led to several different screens, whose requests did not
# all agree. Which request belongs to which move is not recoverable: they
# are stored per interaction but flattened into one list on read.
# Details: docs/dev/generators/user_flows.md#mixed
MIXED = "mixed"


@dataclass(frozen=True)
class FlowTransition:
    """One move between two screens.
    Details: docs/dev/generators/user_flows.md#flowtransition
    """

    from_state: str
    to_state: str
    trigger: str
    action: str
    endpoint: str
    status: Optional[int]
    outcome: str


@dataclass(frozen=True)
class FlowGraph:
    """Every screen the crawl reached and every move it took between them.
    Details: docs/dev/generators/user_flows.md#flowgraph
    """

    states: Tuple[str, ...]
    transitions: Tuple[FlowTransition, ...]
    entry_states: Tuple[str, ...]
    dead_ends: Tuple[str, ...]


def _trigger_label(component: Optional[Dict[str, Any]], path: str) -> str:
    """What a reader would call the control that caused this move.

    Falls back through the same chain the graph's own captions use, and
    lands on the CSS path only when a control genuinely has no text - in
    which case the path is the only honest answer, and is also the thing
    to go look at.
    """
    if not component:
        return path
    return (component.get("text") or component.get("component_type") or path).strip() or path


def _requests_for_move(component: Optional[Dict[str, Any]], to_state: str) -> Tuple[List[Dict[str, Any]], bool]:
    """The requests this specific move fired, and whether that is exact.

    Interactions carry the position they happened at (`VisitStep`), and so
    do the requests they fired, so a control clicked twice can have each
    click's response separated from the other's - which is what stops the
    successful branch being labelled with the failed branch's status.

    Falls back to the control's pooled requests, flagged inexact, when
    nothing is stamped: data written before the stamping existed.
    Details: docs/dev/generators/user_flows.md#_requests_for_move
    """
    if not component:
        return [], True
    matching = [
        interaction
        for interaction in component.get("interactions") or []
        if interaction.get("visit_id")
        and route_shape(interaction.get("resulting_url") or "") == to_state
    ]
    if not matching:
        return list(component.get("network_requests") or []), False
    requests: List[Dict[str, Any]] = []
    for interaction in matching:
        requests.extend(
            requests_for(component, interaction["visit_id"], interaction.get("step_seq") or 0)
        )
    return requests, True


def _is_failure(request: Dict[str, Any]) -> bool:
    status = request.get("status")
    return bool(request.get("failed")) or (isinstance(status, int) and status >= 400)


def _outcomes_agree(requests: Sequence[Dict[str, Any]]) -> bool:
    """Whether every request on one control succeeded, or every one failed."""
    failures = {_is_failure(request) for request in requests}
    return len(failures) <= 1


def _request_outcome(requests: Sequence[Dict[str, Any]]) -> Tuple[str, Optional[int], str]:
    """`(outcome, status, endpoint)` for the requests behind one transition.

    A failed or `>= 400` request wins over a successful one: a screen that
    answers 201 for most inputs and 422 for some is interesting *because*
    of the 422, and a transition summarised by its happy path would hide
    exactly the branch worth documenting.
    Details: docs/dev/generators/user_flows.md#_request_outcome
    """
    if not requests:
        return UNKNOWN, None, ""

    def rank(request: Dict[str, Any]) -> int:
        if _is_failure(request):
            return 0
        return 1 if isinstance(request.get("status"), int) else 2

    chosen = sorted(requests, key=rank)[0]
    status = chosen.get("status")
    endpoint = f"{chosen.get('method', '')} {chosen.get('url', '')}".strip()
    if _is_failure(chosen):
        return ERROR, status, endpoint
    return (OK if isinstance(status, int) else UNKNOWN), status, endpoint


def build_flow_graph(edges: Sequence[Dict[str, str]], components: Sequence[Dict[str, Any]]) -> FlowGraph:
    """Fold the crawl's navigation edges into a deduplicated state machine.

    Args:
        edges: `GraphStore.get_edges` output. Its `component` field holds
            the triggering element's CSS path (see
            `GraphStoreSink.record_navigation_edge`), which is what makes
            the join below possible.
        components: `ledger.flat_component_ledger` output, for the text to
            label a transition with and the requests to annotate it.

    Returns:
        A `FlowGraph`. `GraphStore.record_edge` already deduplicates by
        `(from, to, component, action)` and counts repeats as
        `observation_count` rather than storing them again - the grouping
        here is coarser still, by `(from, to, trigger, action)`, since two
        different components can render the same human-readable `trigger`
        label (e.g. two links with identical visible text on one page
        leading to the same destination) and are worth collapsing into one
        transition in the diagram even though the store keeps them as two
        distinct edges.
    Details: docs/dev/generators/user_flows.md#build_flow_graph
    """
    by_key = {(c.get("page_url"), c.get("path")): c for c in components}
    # A control that led to several different screens can't have its
    # requests attributed to one of them - see MIXED.
    destinations: Dict[Tuple[str, str], set] = {}
    for edge in edges:
        destinations.setdefault((edge.get("from", ""), edge.get("component", "")), set()).add(
            edge.get("to", "")
        )

    seen: Dict[Tuple[str, str, str, str], FlowTransition] = {}
    for edge in edges:
        from_state, to_state = edge.get("from", ""), edge.get("to", "")
        path = edge.get("component", "")
        component = by_key.get((from_state, path))
        trigger = _trigger_label(component, path)
        requests, exact = _requests_for_move(component, to_state)
        outcome, status, endpoint = _request_outcome(requests)
        # Ambiguity only survives where the stamps could not resolve it.
        if not exact and len(destinations[(from_state, path)]) > 1 and not _outcomes_agree(requests):
            outcome, status = MIXED, None
        key = (from_state, to_state, trigger, edge.get("action", ""))
        # An error outcome seen on any repeat of the same move wins - the
        # run where the form was rejected is the informative one.
        if key in seen and seen[key].outcome == ERROR:
            continue
        seen[key] = FlowTransition(
            from_state=from_state, to_state=to_state, trigger=trigger,
            action=edge.get("action", ""), endpoint=endpoint, status=status, outcome=outcome,
        )

    transitions = tuple(sorted(seen.values(), key=lambda t: (t.from_state, t.to_state, t.trigger)))
    states = tuple(sorted({t.from_state for t in transitions} | {t.to_state for t in transitions}))
    with_incoming = {t.to_state for t in transitions}
    with_outgoing = {t.from_state for t in transitions}
    return FlowGraph(
        states=states,
        transitions=transitions,
        entry_states=tuple(s for s in states if s not in with_incoming),
        dead_ends=tuple(s for s in states if s not in with_outgoing),
    )


def _state_ids(states: Sequence[str]) -> Dict[str, str]:
    """Mermaid state identifiers must be plain tokens; real routes aren't."""
    return {state: f"s{index}" for index, state in enumerate(states)}


def render_state_diagram(flow: FlowGraph) -> str:
    """The flow as a Mermaid `stateDiagram-v2`.
    Details: docs/dev/generators/user_flows.md#render_state_diagram
    """
    ids = _state_ids(flow.states)
    lines = ["```mermaid", "stateDiagram-v2"]
    for state, state_id in ids.items():
        lines.append(f'    {state_id} : {state}')
    for entry in flow.entry_states:
        lines.append(f"    [*] --> {ids[entry]}")
    for transition in flow.transitions:
        label = transition.trigger.replace(":", " ").replace("\n", " ")[:40]
        if transition.endpoint:
            label += f" ({transition.endpoint.split('?')[0]}"
            label += f" -> {transition.status})" if transition.status is not None else ")"
        if transition.outcome == ERROR:
            label += " [error]"
        elif transition.outcome == MIXED:
            label += " [outcome not attributable]"
        lines.append(f"    {ids[transition.from_state]} --> {ids[transition.to_state]} : {label}")
    lines.append("```")
    return "\n".join(lines)


def _render_table(flow: FlowGraph) -> List[str]:
    lines = ["| From | Trigger | Action | Endpoint | Status | To |", "|---|---|---|---|---|---|"]
    for t in flow.transitions:
        if t.outcome == MIXED:
            status = "not attributable"
        elif t.outcome == ERROR and t.status is None:
            status = "failed"
        else:
            status = t.status if t.status is not None else "-"
        lines.append(
            f"| {t.from_state} | {t.trigger} | {t.action} | {t.endpoint or '-'} | {status} | {t.to_state} |"
        )
    return lines


@DOCUMENT_REGISTRY.register("flows")
class UserFlowsDocument(DocumentGenerator):
    """Details: docs/dev/generators/user_flows.md#userflowsdocument"""

    name = "flows"
    title = "User Flows"
    purpose = "The state machine the crawl walked: every screen, what moves between them, and which moves fail."

    def generate(self, request: DocumentRequest) -> str:
        flow = build_flow_graph(
            request.graph_store.get_edges(request.site),
            flat_component_ledger(request.graph_store, request.site),
        )
        lines = [f"# User Flows: {request.site}", ""]
        if not flow.transitions:
            lines.append("The crawl recorded no navigation between pages, so there is no flow to draw.")
            return "\n".join(lines) + "\n"

        lines += [
            f"{len(flow.states)} screens, {len(flow.transitions)} distinct moves between them. "
            "States are route shapes, not raw URLs, so many instances of one screen collapse into one node.",
            "",
            "Each request is attributed to the interaction that fired it, using the position both "
            "carry. A move is marked *not attributable* only where that position is missing - a "
            "graph crawled before interactions were stamped - rather than being given a status it "
            "may not have had.",
            "",
            render_state_diagram(flow),
            "",
            "## Transitions",
            "",
        ]
        lines += _render_table(flow)
        lines.append("")

        failures = [t for t in flow.transitions if t.outcome == ERROR]
        if failures:
            lines += [
                "## Error branches",
                "",
                "Moves whose request failed or answered 4xx/5xx. These are the paths a rebuild has to "
                "keep working, and the ones a happy-path diagram would hide.",
                "",
            ]
            lines += [
                f"- `{t.from_state}` -> `{t.to_state}` via **{t.trigger}**: {t.endpoint or 'no request captured'}"
                f" ({t.status if t.status is not None else 'request failed'})"
                for t in failures
            ]
            lines.append("")

        if flow.dead_ends:
            lines += [
                "## Screens with no way out",
                "",
                "No interaction the crawl tried led anywhere from these. Either a genuine dead end - "
                "which is a usability finding - or a screen whose exits the crawl never reached; the "
                "coverage document tells which.",
                "",
            ]
            lines += [f"- {state}" for state in flow.dead_ends]
            lines.append("")
        return "\n".join(lines)
