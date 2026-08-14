"""Ordered traces: the interactions of one page visit, in the order they
happened, each with the requests it actually fired.

This is what `VisitStep` was stamped for. Two documents read it: the
Gherkin specification, whose scenarios *are* traces, and the flow
document, which uses the per-step request attribution to stop labelling a
successful branch with a failed one's status.

Details: docs/dev/generators/traces.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple


@dataclass(frozen=True)
class TraceStep:
    """One interaction, with what it did and what it caused.
    Details: docs/dev/generators/traces.md#tracestep
    """

    page_url: str
    path: str
    label: str
    action: str
    value: str
    resulting_url: str
    requests: Tuple[Dict[str, Any], ...]

    @property
    def navigated(self) -> bool:
        return bool(self.resulting_url) and self.resulting_url != self.page_url


@dataclass(frozen=True)
class Trace:
    """One page visit's interactions, in order.
    Details: docs/dev/generators/traces.md#trace
    """

    visit_id: str
    steps: Tuple[TraceStep, ...]

    @property
    def start_page(self) -> str:
        return self.steps[0].page_url if self.steps else ""

    @property
    def end_page(self) -> str:
        for step in reversed(self.steps):
            if step.navigated:
                return step.resulting_url
        return self.start_page


def _label(component: Dict[str, Any]) -> str:
    """What a person would call this control - text, else role, else path."""
    return (
        (component.get("text") or "").strip()
        or (component.get("component_type") or "").strip()
        or (component.get("path") or "")
    )


def requests_for(component: Dict[str, Any], visit_id: str, step_seq: int) -> List[Dict[str, Any]]:
    """The requests one specific interaction fired, not the control's pooled total.

    Falls back to every request the control ever fired when nothing is
    stamped - data written before `VisitStep` existed, or by a path that
    does not stamp. The caller has to be able to tell those apart, which
    is why this returns the pool rather than nothing: an unattributable
    request is still evidence.
    Details: docs/dev/generators/traces.md#requests_for
    """
    requests = component.get("network_requests") or []
    if not visit_id:
        return list(requests)
    matched = [
        request
        for request in requests
        if request.get("visit_id") == visit_id and request.get("step_seq") == step_seq
    ]
    stamped = [request for request in requests if request.get("visit_id")]
    # Nothing stamped at all means old data, not "this step fired nothing".
    return matched if stamped else list(requests)


def build_traces(components: Sequence[Dict[str, Any]]) -> List[Trace]:
    """Group every stamped interaction into one trace per page visit.

    Args:
        components: `ledger.flat_component_ledger` output.

    Returns:
        One `Trace` per `visit_id`, steps ordered by `step_seq`, longest
        first. Interactions with no `visit_id` are skipped entirely -
        they carry no position, so including them would put them in an
        arbitrary place in a sequence whose whole value is its order.
    Details: docs/dev/generators/traces.md#build_traces
    """
    by_visit: Dict[str, List[Tuple[int, TraceStep]]] = {}
    for component in components:
        for interaction in component.get("interactions") or []:
            visit_id = interaction.get("visit_id") or ""
            if not visit_id:
                continue
            step_seq = interaction.get("step_seq") or 0
            by_visit.setdefault(visit_id, []).append(
                (
                    step_seq,
                    TraceStep(
                        page_url=component.get("page_url", ""),
                        path=component.get("path", ""),
                        label=_label(component),
                        action=interaction.get("action", ""),
                        value=interaction.get("value", ""),
                        resulting_url=interaction.get("resulting_url", ""),
                        requests=tuple(requests_for(component, visit_id, step_seq)),
                    ),
                )
            )

    traces = [
        Trace(visit_id=visit_id, steps=tuple(step for _, step in sorted(steps, key=lambda item: item[0])))
        for visit_id, steps in by_visit.items()
    ]
    return sorted(traces, key=lambda trace: (-len(trace.steps), trace.visit_id))
