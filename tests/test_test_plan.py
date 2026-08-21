"""Unit tests for generators/test_plan.py - closing the loop from gherkin
scenarios to a real staging run (docs/adr/0022)."""
import json

from core.documents import DocumentRequest
from core.interfaces import InferredRequest
from generators.test_plan import (
    TestPlanDocument,
    build_test_plan,
    ingest_cucumber_json,
    normalize_outcome,
)
from utils.schema_validation import validate_against_schema

PAGE = "shop/cart"
ENDPOINT = "shop/api/checkout"
_SCHEMA_PATH = "schemas/test-plan.schema.json"


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


class _Store:
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


def _traceable_request(settings=None):
    """One traceable trace (Pagar triggers `POST shop/api/checkout`) - the
    same fixture shape tests/test_gherkin.py uses, so `build_scenarios`
    writes exactly one real scenario."""
    ledger_components = [
        _component("div > pay", "Pagar", [_interaction(resulting_url="shop/receipt", step_seq=1)], [_request(step_seq=1)]),
    ]
    ledger = {PAGE: {component["path"]: component for component in ledger_components}}
    inferred_requests = [_inferred_request(triggered_by=((PAGE, "div > pay"),))]
    store = _Store(ledger, inferred_requests)
    return DocumentRequest(graph_store=store, site="shop.example", agent=None, settings=settings or {})


def _empty_request():
    return DocumentRequest(graph_store=_Store({}), site="shop.example", agent=None)


# --- normalize_outcome ---

def test_passed_and_failed_map_onto_themselves():
    assert normalize_outcome("passed") == "passed"
    assert normalize_outcome("failed") == "failed"


def test_skipped_reads_as_inapplicable_not_untested():
    """A runner skip is a decision made this run (a tag filter, an
    earlier failure) - distinct from "never staged at all"."""
    assert normalize_outcome("skipped") == "inapplicable"


def test_undefined_pending_and_ambiguous_all_read_as_canttell():
    assert normalize_outcome("undefined") == "cantTell"
    assert normalize_outcome("pending") == "cantTell"
    assert normalize_outcome("ambiguous") == "cantTell"


def test_behaves_own_untested_status_maps_onto_the_same_word():
    assert normalize_outcome("untested") == "untested"


def test_an_unrecognized_status_is_canttell_not_a_silent_guess():
    assert normalize_outcome("some-future-runners-new-status") == "cantTell"


# --- ingest_cucumber_json, against real runner output shapes ---

def _cucumber_js_sample(status="passed"):
    """cucumber-js's own legacy JSON formatter shape: tags as objects
    with a `name` field, `@`-prefixed."""
    return [
        {
            "uri": "features/checkout.feature",
            "keyword": "Feature",
            "name": "Checkout",
            "elements": [
                {
                    "keyword": "Scenario",
                    "name": "User pays for the cart",
                    "tags": [{"name": "@REQ-abc123", "line": 1}, {"name": "@confidence:observed", "line": 1}],
                    "steps": [
                        {"keyword": "Given ", "name": "the user is on \"shop/cart\"", "result": {"status": "passed"}},
                        {"keyword": "When ", "name": "the user clicks \"Pagar\"", "result": {"status": status}},
                    ],
                }
            ],
        }
    ]


def _behave_sample(status="passed"):
    """behave's own JSON formatter shape: tags as bare strings, no `@`,
    no wrapping object - a real, documented difference from cucumber-js.
    """
    return [
        {
            "keyword": "Feature",
            "name": "Checkout",
            "elements": [
                {
                    "keyword": "Scenario",
                    "name": "User pays for the cart",
                    "tags": ["REQ-abc123", "confidence:observed"],
                    "steps": [
                        {"keyword": "Given ", "name": "the user is on \"shop/cart\"", "result": {"status": "passed"}},
                        {"keyword": "When ", "name": "the user clicks \"Pagar\"", "result": {"status": status}},
                    ],
                }
            ],
        }
    ]


def test_cucumber_js_tags_are_read_verbatim_at_prefixed():
    outcomes = ingest_cucumber_json(_cucumber_js_sample())

    assert outcomes == {("@REQ-abc123", "@confidence:observed"): "passed"}


def test_behaves_own_unprefixed_bare_string_tags_normalize_to_the_same_key():
    """behave strips the '@' and emits plain strings, not {"name": ...}
    objects - both dialects must resolve to the identical tag tuple a
    gherkin.py scenario itself carries."""
    outcomes = ingest_cucumber_json(_behave_sample())

    assert outcomes == {("@REQ-abc123", "@confidence:observed"): "passed"}


def test_a_failed_step_makes_the_whole_scenario_failed():
    outcomes = ingest_cucumber_json(_cucumber_js_sample(status="failed"))

    assert outcomes[("@REQ-abc123", "@confidence:observed")] == "failed"


def test_two_elements_sharing_one_tag_tuple_aggregate_to_their_worst_outcome():
    """Every row of one Scenario Outline inherits the Outline's own tags
    - a passing row and a failing row under the same tags must report
    failed, not silently average out or pick the first one seen."""
    document = _cucumber_js_sample(status="passed") + _cucumber_js_sample(status="failed")

    outcomes = ingest_cucumber_json(document)

    assert outcomes[("@REQ-abc123", "@confidence:observed")] == "failed"


def test_a_scenario_with_no_steps_at_all_is_untested():
    document = _cucumber_js_sample()
    document[0]["elements"][0]["steps"] = []

    outcomes = ingest_cucumber_json(document)

    assert outcomes[("@REQ-abc123", "@confidence:observed")] == "untested"


# --- build_test_plan ---

def test_every_traceable_scenario_gets_an_entry_defaulting_to_untested():
    entries = build_test_plan(_traceable_request())

    assert len(entries) == 1
    assert entries[0]["outcome"] == "untested"
    assert entries[0]["tags"][0].startswith("@REQ-")
    assert "@confidence:observed" in entries[0]["tags"]


def test_no_traceable_scenario_means_an_empty_plan_not_an_error():
    assert build_test_plan(_empty_request()) == []


def test_a_supplied_test_result_overrides_the_untested_default():
    request = _traceable_request()
    entries = build_test_plan(request)
    tags = tuple(entries[0]["tags"])

    cucumber_document = [
        {
            "elements": [
                {"tags": [{"name": tag} for tag in tags], "steps": [{"result": {"status": "passed"}}]},
            ],
        }
    ]
    supplied = build_test_plan(DocumentRequest(
        graph_store=request.graph_store, site=request.site, agent=None,
        settings={"test_results": cucumber_document},
    ))

    assert supplied[0]["outcome"] == "passed"


# --- the document ---

def test_generate_returns_a_source_and_a_view_output():
    outputs = TestPlanDocument().outputs(_traceable_request())

    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]


def test_the_view_lists_the_scenario_and_its_outcome():
    view = TestPlanDocument().outputs(_traceable_request())[1].content

    assert "untested" in view


def test_no_scenario_is_stated_narrowly_not_as_a_bare_empty_note():
    view = TestPlanDocument().outputs(_empty_request())[1].content

    assert "gherkin.feature" in view


def test_the_source_output_is_the_same_entries_build_test_plan_produces():
    request = _traceable_request()
    entries = build_test_plan(request)

    source = TestPlanDocument().outputs(request)[0].content

    assert json.loads(source) == entries


def test_the_document_validates_against_its_own_schema():
    entries = build_test_plan(_traceable_request())

    validate_against_schema(entries, _SCHEMA_PATH)
