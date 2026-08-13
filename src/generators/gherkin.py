"""D8: BDD scenarios in Gherkin, and the sequence diagram each one is.

Every Given/When/Then line is rendered from a recorded trace. The model is
asked for one thing only - a business-language title - and never for a
step. A scenario whose steps the model wrote would be a plausible story
about the application rather than a record of it, and the point of this
document is that a runner can execute it against the rebuild.

Honest about its own shape: the crawl is exhaustive, not goal-directed, so
these are scenarios of *what can be done*, not of what a user sets out to
do. Traces are short because a pass stops the moment an interaction
navigates - which is also what makes that cut a natural scenario boundary.

Details: docs/dev/generators/gherkin.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..core.documents import DocumentGenerator, DocumentRequest
from ..core.registry import DOCUMENT_REGISTRY
from .ledger import flat_component_ledger
from .traces import Trace, TraceStep, build_traces

TITLE_SYSTEM_INSTRUCTION = (
    "You name one scenario of a web application from a list of the steps a user took and the API "
    "calls those produced. Reply with a single short title line in business language - no Gherkin "
    "keywords, no quotes, no explanation, under 12 words. Describe what the user achieved, not "
    "which elements were clicked. Never invent a step that is not listed."
)

_NO_TRACES_NOTE = (
    "No ordered interaction traces were recorded. Scenarios are built from interactions stamped "
    "with their position in a visit; a crawl predating that stamping has the interactions but not "
    "the order, and an unordered scenario is not a scenario."
)

_PREAMBLE = (
    "Generated from recorded interaction traces. Every Given/When/Then is rendered from what the",
    "crawl observed - the model was asked only for scenario titles, never for a step, so each line",
    "asserts what happened rather than what plausibly might have.",
    "",
    "These describe what CAN be done rather than what a user sets out to do: the crawl is",
    "exhaustive, not goal-directed, and a pass ends the moment an interaction navigates - which is",
    "also what makes that cut a natural scenario boundary.",
)


def _is_observable(trace: Trace) -> bool:
    """Whether anything happened worth writing a scenario about.

    A pass whose every interaction changed nothing and called nothing is
    real crawl history and an empty specification; keeping it would bury
    the scenarios that matter under ones asserting nothing.
    Details: docs/dev/generators/gherkin.md#_is_observable
    """
    return any(step.navigated or step.requests for step in trace.steps)


def _quoted(value: str) -> str:
    """Gherkin delimits step arguments with double quotes, so one inside a
    button's own label would close the argument early."""
    return value.replace('"', "'")


def _when_line(step: TraceStep, first: bool) -> str:
    keyword = "When" if first else "And"
    if step.action == "fill":
        return f'{keyword} the user enters "{_quoted(step.value)}" into "{_quoted(step.label)}"'
    return f'{keyword} the user {step.action}s "{_quoted(step.label)}"'


def _then_lines(trace: Trace) -> List[str]:
    """One assertion per observed effect, in the order it was observed."""
    lines: List[str] = []
    for step in trace.steps:
        for request in step.requests:
            method = request.get("method", "")
            url = (request.get("url") or "").split("?")[0]
            status = request.get("status")
            keyword = "Then" if not lines else "And"
            if request.get("failed"):
                lines.append(f"{keyword} the request {method} {url} fails")
            elif status is not None:
                lines.append(f"{keyword} the response to {method} {url} is {status}")
            else:
                lines.append(f"{keyword} the client sends {method} {url}")
    if trace.end_page != trace.start_page:
        keyword = "Then" if not lines else "And"
        lines.append(f'{keyword} the user is on "{_quoted(trace.end_page)}"')
    return lines


def render_scenario(trace: Trace, title: str) -> str:
    """One Gherkin scenario, entirely from the trace.
    Details: docs/dev/generators/gherkin.md#render_scenario
    """
    lines = [f"  Scenario: {title}", f'    Given the user is on "{_quoted(trace.start_page)}"']
    lines += [f"    {_when_line(step, first=index == 0)}" for index, step in enumerate(trace.steps)]
    lines += [f"    {line}" for line in _then_lines(trace)]
    return "\n".join(lines)


def render_sequence_diagram(trace: Trace) -> str:
    """The same trace as a UML sequence diagram.

    Not a second source of truth - the same steps, drawn. A trace already
    *is* a sequence (actor, control, endpoint, response, over time), which
    is why this costs no extra query and cannot disagree with the scenario.
    Details: docs/dev/generators/gherkin.md#render_sequence_diagram
    """
    lines = ["```mermaid", "sequenceDiagram", "    actor User", "    participant UI", "    participant API"]
    for step in trace.steps:
        lines.append(f"    User->>UI: {step.action} {_quoted(step.label)[:40]}")
        for request in step.requests:
            url = (request.get("url") or "").split("?")[0]
            lines.append(f"    UI->>API: {request.get('method', '')} {url}")
            status = request.get("status")
            if request.get("failed"):
                answer = "request failed"
            else:
                answer = str(status) if status is not None else "no response captured"
            lines.append(f"    API-->>UI: {answer}")
        if step.navigated:
            lines.append(f"    UI-->>User: {_quoted(step.resulting_url)[:40]}")
    lines.append("```")
    return "\n".join(lines)


def _fallback_title(trace: Trace) -> str:
    """A title from the trace itself - poorer than a narrated one, never wrong.
    Used when no model is wired, and when a narration call fails."""
    first = trace.steps[0]
    where = trace.end_page if trace.end_page != trace.start_page else trace.start_page
    return f"{first.action} {first.label} on {where}".strip()


def _prompt_line(step: TraceStep) -> str:
    """One step, as the model sees it when naming a scenario."""
    methods = ", ".join(request.get("method", "?") for request in step.requests)
    return f"- {step.action} {step.label}" + (f" -> {methods}" if methods else "")


def narrate_titles(agent: Any, traces: Sequence[Trace]) -> Dict[str, str]:
    """One `generate()` call per scenario, for its title and nothing else.
    A failure degrades that one title to the deterministic fallback rather
    than costing the document.
    Details: docs/dev/generators/gherkin.md#narrate_titles
    """
    titles: Dict[str, str] = {}
    for trace in traces:
        steps = "\n".join(_prompt_line(step) for step in trace.steps)
        prompt = (
            f"Starting page: {trace.start_page}\n"
            f"Steps:\n{steps}\n"
            f"Ends on: {trace.end_page}"
        )
        try:
            answer = agent.generate(prompt, system_instruction=TITLE_SYSTEM_INSTRUCTION).strip()
        except Exception:  # noqa: BLE001 - one poor title beats losing the document
            answer = ""
        titles[trace.visit_id] = answer.splitlines()[0].strip(' "') if answer else _fallback_title(trace)
    return titles


def _observable_traces(request: DocumentRequest) -> List[Trace]:
    components = flat_component_ledger(request.graph_store, request.site)
    return [trace for trace in build_traces(components) if _is_observable(trace)]


def _titles_for(request: DocumentRequest, traces: Sequence[Trace]) -> Dict[str, str]:
    if request.agent is None:
        return {trace.visit_id: _fallback_title(trace) for trace in traces}
    return narrate_titles(request.agent, traces)


@DOCUMENT_REGISTRY.register("gherkin")
class GherkinDocument(DocumentGenerator):
    """A real `.feature` file, not Gherkin quoted inside prose.
    Details: docs/dev/generators/gherkin.md#gherkindocument
    """

    name = "gherkin"
    title = "Behaviour Specification"
    purpose = "Executable BDD scenarios, one per recorded interaction sequence - a .feature a runner can execute."
    extension = "feature"

    def generate(self, request: DocumentRequest) -> str:
        traces = _observable_traces(request)
        if not traces:
            return f"# {_NO_TRACES_NOTE}\n"
        titles = _titles_for(request, traces)
        lines = [f"# {line}".rstrip() for line in _PREAMBLE]
        lines += ["", f"Feature: {request.site}", ""]
        lines += [render_scenario(trace, titles[trace.visit_id]) + "\n" for trace in traces]
        return "\n".join(lines)


@DOCUMENT_REGISTRY.register("sequences")
class SequenceDiagramsDocument(DocumentGenerator):
    """The same traces as UML sequence diagrams, in Markdown.
    Details: docs/dev/generators/gherkin.md#sequencediagramsdocument
    """

    name = "sequences"
    title = "Sequence Diagrams"
    purpose = "Each recorded interaction sequence drawn as a UML sequence diagram - actor, UI, API, response."

    def generate(self, request: DocumentRequest) -> str:
        traces = _observable_traces(request)
        lines = [f"# Sequence Diagrams: {request.site}", ""]
        if not traces:
            lines.append(_NO_TRACES_NOTE)
            return "\n".join(lines) + "\n"
        titles = _titles_for(request, traces)
        lines += [
            "The same traces the behaviour specification renders as scenarios, drawn. Not a second "
            "source of truth - a trace already *is* a sequence, so these cannot disagree with it.",
            "",
        ]
        for trace in traces:
            lines += [f"## {titles[trace.visit_id]}", "", render_sequence_diagram(trace), ""]
        return "\n".join(lines)
