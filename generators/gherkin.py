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

**This module stays a pure trace-shape renderer** (a `Trace` and a title
in, Gherkin/Mermaid text out) - no store, no graph metrics. `Scenario
Outline`/`Examples` dedup (docs/adr/0013 point 4) lives here too, since it
only ever reshapes a `Trace`'s own fields. The store-dependent half of
ADR-0013 - correlating a trace to `requirements.py`'s extraction rules and
to the graph's module/screen ids for `@REQ-<hash>`/`@EP-<hash>`/
`@MOD-<x>`/`@SCR-<hash>` tags - lives in `generators/gherkin_tags.py`, and
`GherkinDocument.generate` is the one place that wires the two together.

`Background` stays unused: it is reserved for setup common to every
scenario in one `Feature` file, and this crawl has no
authentication-precondition (or other state) instrumentation to back one
honestly - every trace can start on a different page, so there is no real
common `Given` to extract.

Details: docs/dev/generators/gherkin.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Sequence

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.short_hash import short_hash
from utils.urls import route_shape
from .gherkin_tags import correlate_trace, module_tags, screen_module_ids, screen_tags, tag_line
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

_NO_TRACEABLE_NOTE = (
    "Interaction traces were recorded, but none correlate to a requirements.json extraction rule. "
    "@REQ-<hash> is a required tag (docs/adr/0013 point 3) - no scenario is written rather than one "
    "carrying a missing or fabricated citation."
)

_PREAMBLE = (
    "Generated from recorded interaction traces. Every Given/When/Then is rendered from what the",
    "crawl observed - the model was asked only for scenario titles, never for a step, so each line",
    "asserts what happened rather than what plausibly might have.",
    "",
    "These describe what CAN be done rather than what a user sets out to do: the crawl is",
    "exhaustive, not goal-directed, and a pass ends the moment an interaction navigates - which is",
    "also what makes that cut a natural scenario boundary.",
    "",
    "Every scenario is tagged @REQ-<hash>, citing the requirements.json entry it demonstrates -",
    "traces with no such correlation are not written here (see the count below, if any).",
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


def _table_cell(value: str) -> str:
    """Escape one `Examples:` table cell - `|` is the column delimiter, and
    a literal newline would break the row across two lines.
    Details: docs/dev/generators/gherkin.md#_table_cell
    """
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")


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
    """One Gherkin scenario, entirely from the trace. No tag line - the
    caller (`GherkinDocument.generate`) prepends one, since the identical
    body also serves as a `Scenario Outline`'s template
    (`render_scenario_outline`).
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
    if traces:
        print(f"Titling {len(traces)} scenarios ({len(traces)} model calls)...")
    for scenario_number, trace in enumerate(traces, 1):
        print(f"  scenario {scenario_number}/{len(traces)}: {trace.start_page} -> {trace.end_page}")
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
    components = flat_component_ledger(request.graph_store)
    return [trace for trace in build_traces(components) if _is_observable(trace)]


def _titles_for(request: DocumentRequest, traces: Sequence[Trace]) -> Dict[str, str]:
    if request.agent is None:
        return {trace.visit_id: _fallback_title(trace) for trace in traces}
    return narrate_titles(request.agent, traces)


# --- Scenario Outline dedup (docs/adr/0013 point 4) ---


def _structural_signature(trace: Trace) -> str:
    """A trace's shape with every concrete value stripped: which route
    each step happened on, which control, what it fired, and which route
    it navigated to - never the literal value typed or the literal
    url/destination visited. The same role-and-hierarchy-only idea
    `generators/aria_tree.py::_structural_shape` uses for `template_hash`
    (ADR-0003), applied to a trace.

    `route_shape(step.resulting_url)` per step, not a single trailing
    "did it navigate anywhere" boolean: two traces landing on genuinely
    different routes (`shop/receipt` vs `shop/help`) are different
    patterns, even though both "navigated somewhere."
    Details: docs/dev/generators/gherkin.md#_structural_signature
    """
    shape = [
        [
            route_shape(step.page_url), step.action, step.label,
            sorted(
                (
                    request.get("method", ""),
                    route_shape((request.get("url") or "").split("?")[0]),
                    request.get("status"),
                    bool(request.get("failed")),
                )
                for request in step.requests
            ),
            route_shape(step.resulting_url) if step.navigated else "",
        ]
        for step in trace.steps
    ]
    return short_hash(json.dumps(shape, sort_keys=False))


def _group_by_pattern(traces: Sequence[Trace]) -> List[List[Trace]]:
    """Traces sharing one structural signature, grouped in first-seen
    order - `Scenario Outline` candidates once a group has 2+ members.
    Details: docs/dev/generators/gherkin.md#_group_by_pattern
    """
    groups: Dict[str, List[Trace]] = {}
    order: List[str] = []
    for trace in traces:
        signature = _structural_signature(trace)
        if signature not in groups:
            order.append(signature)
        groups.setdefault(signature, []).append(trace)
    return [groups[signature] for signature in order]


def _templated_trace(group: Sequence[Trace]) -> Trace:
    """One representative `Trace` for the group's `Outline` body -
    identical to every member except a field that genuinely varies across
    the group is replaced with a `<placeholder>` token.

    A Gherkin placeholder is just literal `<name>` text sitting where a
    concrete value otherwise would; `render_scenario`/`_when_line`/
    `_then_lines` already interpolate whatever string is in
    `.value`/`.requests[...]['url']`/`.resulting_url` verbatim, so this
    synthetic trace renders correctly through the exact same renderers a
    plain `Scenario` uses - no parallel templated-rendering path needed.
    Details: docs/dev/generators/gherkin.md#_templated_trace
    """
    representative = group[0]
    steps = []
    for index, step in enumerate(representative.steps):
        value = step.value
        if len({member.steps[index].value for member in group}) > 1:
            value = f"<value_{index + 1}>"

        requests = []
        for request_index, request in enumerate(step.requests):
            urls = {member.steps[index].requests[request_index].get("url", "") for member in group}
            requests.append({**request, "url": f"<url_{index + 1}_{request_index + 1}>"} if len(urls) > 1 else request)

        resulting_url = step.resulting_url
        if len({member.steps[index].resulting_url for member in group}) > 1:
            resulting_url = f"<destination_{index + 1}>"

        steps.append(replace(step, value=value, requests=tuple(requests), resulting_url=resulting_url))
    return replace(representative, steps=tuple(steps))


def _placeholder_row(templated: Trace, actual: Trace) -> Dict[str, str]:
    """One `Examples:` row - the concrete value `actual` contributes for
    every placeholder `_templated_trace` introduced. Every trace in a
    group produces a row with the identical key set, since the group
    shares one structural signature and therefore one placeholder layout.
    Details: docs/dev/generators/gherkin.md#_placeholder_row
    """
    row: Dict[str, str] = {}
    for index, (templated_step, actual_step) in enumerate(zip(templated.steps, actual.steps)):
        if templated_step.value != actual_step.value:
            row[f"value_{index + 1}"] = actual_step.value
        for request_index, (templated_request, actual_request) in enumerate(
            zip(templated_step.requests, actual_step.requests)
        ):
            if templated_request.get("url", "") != actual_request.get("url", ""):
                row[f"url_{index + 1}_{request_index + 1}"] = (actual_request.get("url") or "").split("?")[0]
        if templated_step.resulting_url != actual_step.resulting_url:
            row[f"destination_{index + 1}"] = actual_step.resulting_url
    return row


def render_scenario_outline(group: Sequence[Trace], title: str, tags_line: str) -> str:
    """`Scenario Outline` + `Examples` (ADR-0013 point 4): one templated
    body shared by every occurrence of the same interaction pattern, one
    concrete row per occurrence - not N near-duplicate `Scenario`s.
    Details: docs/dev/generators/gherkin.md#render_scenario_outline
    """
    templated = _templated_trace(group)
    body = render_scenario(templated, title).replace("Scenario:", "Scenario Outline:", 1)
    rows = [_placeholder_row(templated, trace) for trace in group]
    columns = sorted(rows[0])
    lines = [tags_line, body, "", "    Examples:", "      | " + " | ".join(columns) + " |"]
    lines += ["      | " + " | ".join(_table_cell(_quoted(row[column])) for column in columns) + " |" for row in rows]
    return "\n".join(lines)


@DOCUMENT_REGISTRY.register("gherkin")
class GherkinDocument(DocumentGenerator):
    """A real `.feature` file, not Gherkin quoted inside prose.
    Details: docs/dev/generators/gherkin.md#gherkindocument
    """

    name = "gherkin"
    title = "Behaviour Specification"
    purpose = "Executable BDD scenarios, one per recorded interaction pattern - a .feature a runner can execute."
    extension = "feature"

    def generate(self, request: DocumentRequest) -> str:
        traces = _observable_traces(request)
        if not traces:
            return f"# {_NO_TRACES_NOTE}\n"

        store = request.graph_store
        correlations_by_visit = {trace.visit_id: correlate_trace(store, trace) for trace in traces}
        traceable = [trace for trace in traces if correlations_by_visit[trace.visit_id].requirement_ids]
        excluded = len(traces) - len(traceable)
        if not traceable:
            lines = [f"# {_NO_TRACEABLE_NOTE}\n"]
            return "\n".join(lines)

        groups = _group_by_pattern(traceable)
        representatives = [group[0] for group in groups]
        titles = _titles_for(request, representatives)
        module_ids = screen_module_ids(request)

        lines = [f"# {line}".rstrip() for line in _PREAMBLE]
        if excluded:
            lines += [
                "#",
                f"# {excluded} observed trace(s) excluded: no requirements.json extraction rule "
                "correlates to them.",
            ]
        lines += ["", f"Feature: {request.site}", ""]

        for group in groups:
            representative = group[0]
            line = tag_line(
                correlations_by_visit[representative.visit_id],
                module_tags(module_ids, representative),
                screen_tags(representative),
            )
            title = titles[representative.visit_id]
            if len(group) >= 2:
                lines.append(render_scenario_outline(group, title, line) + "\n")
            else:
                lines.append(line + "\n" + render_scenario(representative, title) + "\n")

        return "\n".join(lines)


@DOCUMENT_REGISTRY.register("sequences")
class SequenceDiagramsDocument(DocumentGenerator):
    """The same traces as UML sequence diagrams, in Markdown.

    Untouched by docs/adr/0013: that ADR locks `gherkin`'s own tag
    vocabulary and `Outline` dedup convention, not this document's shape -
    every observable trace still gets its own diagram, undeduplicated and
    untagged.
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
