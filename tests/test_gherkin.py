"""Unit tests for the Gherkin specification and its `Scenario Outline`
dedup (docs/adr/0013 point 4). The .feature output is checked with the
real Cucumber parser, not by asserting substrings.

Trace construction has its own tests in tests/test_traces.py. The
store-dependent half of ADR-0013 (correlating a trace to
requirements.py's extraction rules and to the graph's module/screen ids)
has its own tests in tests/test_gherkin_tags.py."""
from gherkin.parser import Parser
from gherkin.token_scanner import TokenScanner

from core.documents import DocumentRequest
from core.interfaces import InferredRequest
from generators.gherkin import (
    GherkinDocument,
    _group_by_pattern,
    _structural_signature,
    render_scenario,
    render_scenario_outline,
)
from generators.traces import build_traces

PAGE = "shop/cart"
ENDPOINT = "shop/api/checkout"


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


def _request(status=201, visit_id="v1", step_seq=1, failed=False, url=None):
    return {
        "method": "POST", "url": url or f"https://{ENDPOINT}", "status": status,
        "failed": failed, "visit_id": visit_id, "step_seq": step_seq,
    }


def _inferred_request(**overrides):
    defaults = dict(
        method="POST", endpoint=ENDPOINT, query_params=(), body_shape="", response_shape="",
        triggered_by=(), loaded_by=(), status_codes=(),
    )
    defaults.update(overrides)
    return InferredRequest(**defaults)


def _parse(feature_text):
    return Parser().parse(TokenScanner(feature_text))


class _Store:
    """A minimal store fixture wiring the component ledger a trace comes
    from to the `InferredRequest` data `_correlate_trace` needs - a
    checkout click only earns a `@REQ-<hash>` tag when this store's own
    `get_inferred_requests()` says the same `(page, path)` triggered it,
    the exact correlation `GherkinDocument.generate()` performs."""

    def __init__(self, ledger, inferred_requests=(), pages=(), edges=()):
        self._ledger = ledger
        self._inferred_requests = list(inferred_requests)
        self._pages = list(pages)
        self._edges = list(edges)

    def get_component_ledger(self):
        return self._ledger

    def get_inferred_requests(self):
        return self._inferred_requests

    def get_progress_table_rows(self):
        return self._pages

    def get_edges(self):
        return self._edges


def _ledger_components():
    return [
        _component("input#q", "Cupon", [_interaction(action="fill", value="DESC10", step_seq=1)]),
        _component("div > pay", "Pagar",
                   [_interaction(resulting_url="shop/receipt", step_seq=2)],
                   [_request(step_seq=2)]),
    ]


def _request_for_store(agent=None, inferred_requests=None, pages=(), edges=()):
    """One traceable trace (Cupon then Pagar, Pagar triggers `POST
    shop/api/checkout`) - the default `inferred_requests` correlates it,
    so `GherkinDocument.generate()` writes a real scenario rather than
    excluding it."""
    ledger = {PAGE: {component["path"]: component for component in _ledger_components()}}
    if inferred_requests is None:
        inferred_requests = [_inferred_request(triggered_by=((PAGE, "div > pay"),))]
    store = _Store(ledger, inferred_requests, pages, edges)
    return DocumentRequest(graph_store=store, site="shop.example", agent=agent)


# --- Scenario Outline dedup (ADR-0013 point 4) ---

def test_structural_signature_matches_for_traces_differing_only_in_value():
    a = build_traces([_component("input#q", "Cupon", [_interaction(action="fill", value="DESC10")])])[0]
    b = build_traces([_component("input#q", "Cupon", [_interaction(action="fill", value="OTHER5")])])[0]

    assert _structural_signature(a) == _structural_signature(b)


def test_structural_signature_differs_for_a_different_action():
    a = build_traces([_component("input#q", "Cupon", [_interaction(action="fill", value="DESC10")])])[0]
    b = build_traces([_component("input#q", "Cupon", [_interaction(action="click")])])[0]

    assert _structural_signature(a) != _structural_signature(b)


def test_structural_signature_differs_for_a_different_destination_route():
    """The route matters, not the literal url - two receipts under
    different order ids would still be `_group_by_pattern`'s point, but a
    genuinely different destination *route* is a different pattern."""
    a = build_traces([_component("a", "Go", [_interaction(resulting_url="shop/receipt")])])[0]
    b = build_traces([_component("a", "Go", [_interaction(resulting_url="shop/help")])])[0]

    assert _structural_signature(a) != _structural_signature(b)


def test_group_by_pattern_collapses_identical_shapes_and_preserves_order():
    traces = build_traces([
        _component("input#q", "Cupon", [_interaction(action="fill", value="A", visit_id="v1")]),
        _component("input#q", "Cupon", [_interaction(action="fill", value="B", visit_id="v2")]),
        _component("a", "Go", [_interaction(resulting_url="shop/help", visit_id="v3")]),
    ])

    groups = _group_by_pattern(traces)

    assert [len(group) for group in groups] == [2, 1]


def test_render_scenario_outline_produces_valid_gherkin_with_one_row_per_trace():
    group = build_traces([
        _component("input#q", "Cupon", [_interaction(action="fill", value="DESC10", visit_id="v1")]),
        _component("input#q", "Cupon", [_interaction(action="fill", value="OTHER5", visit_id="v2")]),
    ])

    outline = render_scenario_outline(group, "Apply a coupon", "  @REQ-x @confidence:observed")
    text = "Feature: t\n\n" + outline + "\n"
    document = _parse(text)

    scenario = document["feature"]["children"][0]["scenario"]
    assert scenario["keyword"] == "Scenario Outline"
    assert len(scenario["examples"][0]["tableBody"]) == 2


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


def test_the_scenario_is_tagged_with_the_correlated_requirement():
    document = _parse(GherkinDocument().generate(_request_for_store()))

    tags = [tag["name"] for tag in document["feature"]["children"][0]["scenario"]["tags"]]

    assert any(tag.startswith("@REQ-") for tag in tags)
    assert "@confidence:observed" in tags
    assert any(tag.startswith("@EP-") for tag in tags)


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
    class _NoopStore:
        def get_component_ledger(self):
            return {PAGE: {"a": _component("a", "Noop", [_interaction()])}}

    text = GherkinDocument().generate(
        DocumentRequest(graph_store=_NoopStore(), site="shop.example", agent=None)
    )

    assert "No ordered interaction traces" in text


def test_a_crawl_with_no_stamped_interactions_explains_itself():
    class _EmptyStore:
        def get_component_ledger(self):
            return {}

    text = GherkinDocument().generate(
        DocumentRequest(graph_store=_EmptyStore(), site="shop.example", agent=None)
    )

    assert "an unordered scenario is not a scenario" in text


def test_an_uncorrelated_trace_is_excluded_and_counted():
    """@REQ-<hash> is required (ADR-0013 point 3) - a trace with no real
    extraction-rule correlation is not written as a half-tagged scenario."""
    request = _request_for_store(inferred_requests=[])

    text = GherkinDocument().generate(request)

    assert "Interaction traces were recorded, but none correlate" in text


def test_some_correlated_and_some_not_reports_the_excluded_count():
    components = _ledger_components() + [
        _component("a#other", "Unrelated", [_interaction(resulting_url="shop/other", visit_id="v2")])
    ]
    ledger = {PAGE: {component["path"]: component for component in components}}
    inferred = [_inferred_request(triggered_by=((PAGE, "div > pay"),))]
    request = DocumentRequest(graph_store=_Store(ledger, inferred), site="shop.example", agent=None)

    text = GherkinDocument().generate(request)

    assert "Scenario:" in text
    assert "1 observed trace(s) excluded" in text


def test_two_structurally_identical_traceable_traces_become_one_outline():
    """`flat_component_ledger` expects one component dict per path, so two
    visits interacting with the same control are two stamped
    interactions on that one component - not two separate components."""
    component = _component(
        "input#q", "Cupon",
        [
            _interaction(action="fill", value="DESC10", visit_id="v1", step_seq=1),
            _interaction(action="fill", value="OTHER5", visit_id="v2", step_seq=1),
        ],
        [_request(step_seq=1, visit_id="v1"), _request(step_seq=1, visit_id="v2")],
    )
    ledger = {PAGE: {"input#q": component}}
    inferred = [_inferred_request(triggered_by=((PAGE, "input#q"),))]
    request = DocumentRequest(graph_store=_Store(ledger, inferred), site="shop.example", agent=None)

    document = _parse(GherkinDocument().generate(request))

    assert len(document["feature"]["children"]) == 1
    assert document["feature"]["children"][0]["scenario"]["keyword"] == "Scenario Outline"
    assert len(document["feature"]["children"][0]["scenario"]["examples"][0]["tableBody"]) == 2


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
