"""Unit tests for traces, the Gherkin specification and its sequence
diagrams (src/generators/traces.py, gherkin.py). The .feature output is
checked with the real Cucumber parser, not by asserting substrings."""
import pytest

from src.core.documents import DocumentRequest
from src.generators.gherkin import (
    GherkinDocument,
    SequenceDiagramsDocument,
    render_scenario,
    render_sequence_diagram,
)
from src.generators.traces import build_traces, requests_for

gherkin_parser = pytest.importorskip("gherkin.parser")
from gherkin.token_scanner import TokenScanner  # noqa: E402

PAGE = "shop/cart"


def _component(path, text, interactions, requests=()):
    return {
        "page_url": PAGE, "path": path, "text": text, "component_type": "button",
        "interactions": list(interactions), "network_requests": list(requests),
    }


def _interaction(action="click", value="", resulting_url="", visit_id="v1", step_seq=1):
    return {
        "action": action, "value": value, "resulting_url": resulting_url,
        "source_path": "", "visit_id": visit_id, "step_seq": step_seq,
    }


def _request(status=201, visit_id="v1", step_seq=1, failed=False):
    return {
        "method": "POST", "url": "https://api/x/checkout", "status": status,
        "failed": failed, "visit_id": visit_id, "step_seq": step_seq,
    }


def _parse(feature_text):
    return gherkin_parser.Parser().parse(TokenScanner(feature_text))


# --- traces ---

def test_steps_are_ordered_by_their_recorded_position():
    """The whole point: "+ + -" and "- + +" were indistinguishable before."""
    components = [
        _component("b", "Second", [_interaction(step_seq=2)]),
        _component("a", "First", [_interaction(step_seq=1)]),
    ]

    trace = build_traces(components)[0]

    assert [step.label for step in trace.steps] == ["First", "Second"]


def test_interactions_from_different_visits_are_different_traces():
    components = [
        _component("a", "A", [_interaction(visit_id="v1", step_seq=1)]),
        _component("b", "B", [_interaction(visit_id="v2", step_seq=1)]),
    ]

    assert len(build_traces(components)) == 2


def test_unstamped_interactions_are_skipped_entirely():
    """They carry no position, so including them would place them
    arbitrarily in a sequence whose whole value is its order."""
    components = [_component("a", "A", [{"action": "click", "visit_id": "", "step_seq": 0}])]

    assert build_traces(components) == []


def test_a_request_is_attributed_to_the_interaction_that_fired_it():
    component = _component("a", "Pay", [], [_request(step_seq=1), _request(status=422, step_seq=2)])

    assert [r["status"] for r in requests_for(component, "v1", 1)] == [201]
    assert [r["status"] for r in requests_for(component, "v1", 2)] == [422]


def test_unstamped_requests_fall_back_to_the_whole_pool():
    """Old data: an unattributable request is still evidence, and returning
    nothing would silently drop it."""
    component = _component("a", "Pay", [], [{"method": "POST", "url": "u", "status": 201}])

    assert len(requests_for(component, "v1", 1)) == 1


# --- the .feature ---

def test_the_generated_feature_parses_with_the_real_gherkin_parser():
    document = _parse(GherkinDocument().generate(_request_for_store()))

    assert document["feature"]["name"] == "shop.example"
    assert len(document["feature"]["children"]) == 1


def test_a_scenario_keeps_the_steps_in_the_order_they_happened():
    document = _parse(GherkinDocument().generate(_request_for_store()))

    steps = document["feature"]["children"][0]["scenario"]["steps"]
    keywords = [step["keyword"].strip() for step in steps]
    texts = [step["text"] for step in steps]

    assert keywords == ["Given", "When", "And", "Then", "And"]
    assert "DESC10" in texts[1]
    assert "Pagar" in texts[2]


def test_a_quote_in_a_control_label_does_not_break_the_feature():
    """Gherkin delimits step arguments with double quotes; one inside a
    button's own label would close the argument early."""
    components = [_component("a", 'Buy "now"', [_interaction(resulting_url="shop/receipt")])]
    trace = build_traces(components)[0]

    text = "Feature: t\n\n" + render_scenario(trace, "title") + "\n"

    assert _parse(text)["feature"]["children"]


def test_a_trace_that_changed_nothing_is_left_out():
    """A pass that navigated nowhere and called nothing is an empty
    specification - keeping it would bury the scenarios that matter."""
    class _Store:
        def get_component_ledger(self, site):
            return {PAGE: {"a": _component("a", "Noop", [_interaction()])}}

    text = GherkinDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "No ordered interaction traces" in text


def test_a_crawl_with_no_stamped_interactions_explains_itself():
    class _Store:
        def get_component_ledger(self, site):
            return {}

    text = GherkinDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "an unordered scenario is not a scenario" in text


# --- titles ---

def test_the_model_is_asked_for_a_title_and_nothing_else():
    """A scenario whose steps the model wrote would be a plausible story
    rather than a record - so the steps must not depend on it."""
    class _Agent:
        prompts = []

        def generate(self, prompt, system_instruction=None):
            self.prompts.append((prompt, system_instruction))
            return "Customer completes checkout"

    agent = _Agent()
    text = GherkinDocument().generate(_request_for_store(agent))

    assert "Scenario: Customer completes checkout" in text
    assert "never invent a step" in agent.prompts[0][1].lower()


def test_a_failed_title_call_degrades_to_the_deterministic_one():
    class _Agent:
        def generate(self, prompt, system_instruction=None):
            raise RuntimeError("model down")

    text = GherkinDocument().generate(_request_for_store(_Agent()))

    assert _parse(text)["feature"]["children"]
    assert "Scenario:" in text


# --- sequence diagrams ---

def test_the_diagram_shows_the_actor_the_ui_and_the_api():
    trace = build_traces(_ledger_components())[0]

    diagram = render_sequence_diagram(trace)

    assert "sequenceDiagram" in diagram
    assert "User->>UI: fill" in diagram
    assert "UI->>API: POST https://api/x/checkout" in diagram
    assert "API-->>UI: 201" in diagram


def test_a_failed_request_is_drawn_as_a_failure_not_a_blank():
    components = [_component("a", "Pay", [_interaction(resulting_url="shop/x")],
                             [_request(status=None, failed=True)])]

    diagram = render_sequence_diagram(build_traces(components)[0])

    assert "API-->>UI: request failed" in diagram


def test_the_diagrams_document_names_each_trace_the_same_way():
    text = SequenceDiagramsDocument().generate(_request_for_store())

    assert "cannot disagree with it" in text
    assert "sequenceDiagram" in text


# --- shared fixtures ---

def _ledger_components():
    return [
        _component("input#q", "Cupon", [_interaction(action="fill", value="DESC10", step_seq=1)]),
        _component("div > pay", "Pagar",
                   [_interaction(resulting_url="shop/receipt", step_seq=2)],
                   [_request(step_seq=2)]),
    ]


def _request_for_store(agent=None):
    class _Store:
        def get_component_ledger(self, site):
            return {PAGE: {component["path"]: component for component in _ledger_components()}}

    return DocumentRequest(graph_store=_Store(), site="shop.example", agent=agent)
