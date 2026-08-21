"""Unit tests for generators/confidence_summary.py - derived confidence
rollups citing each source by reference (docs/adr/0029).

`_prd_rollup`/`_data_model_rollup`/`_level_rollup` are tested directly
against hand-built documents rather than the full store-dependent
requirements/data-model/usability/accessibility pipelines - those
pipelines already have their own test suites; this module's own job is
the aggregation, not re-deriving what triggers a finding."""
from core.documents import DocumentRequest
from generators.confidence_summary import (
    ConfidenceSummaryDocument,
    _data_model_rollup,
    _level_rollup,
    _prd_rollup,
    build_confidence_summary,
)
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/confidence-summary.schema.json"


def _requirement(confidence):
    return {"id": f"REQ-{confidence}", "confidence": confidence}


def _request():
    return DocumentRequest(graph_store=None, site="shop.example", agent=None, settings={"run_id": "RUN-1"})


# --- _prd_rollup ---

def test_percentages_match_a_hand_computed_fixture(monkeypatch):
    """The ticket's own Done-when criterion: rollups match hand-computed
    percentages against a fixture. 2 observed, 1 inferred, 1 assumed of
    4 total -> 50%/25%/25%."""
    import generators.confidence_summary as confidence_summary_module

    document = {
        "requirements": [
            _requirement("observed"), _requirement("observed"),
            _requirement("inferred"), _requirement("assumed"),
        ]
    }
    monkeypatch.setattr(confidence_summary_module, "build_requirements_document", lambda request: document)

    rollup = _prd_rollup(_request())

    assert rollup == {
        "source_document": "requirements",
        "by_confidence": {"observed": 2, "inferred": 1, "assumed": 1},
        "total": 4,
    }
    assert rollup["by_confidence"]["observed"] / rollup["total"] == 0.5


def test_no_requirements_rolls_up_to_all_zero_counts(monkeypatch):
    import generators.confidence_summary as confidence_summary_module

    monkeypatch.setattr(confidence_summary_module, "build_requirements_document", lambda request: {"requirements": []})

    rollup = _prd_rollup(_request())

    assert rollup["by_confidence"] == {"observed": 0, "inferred": 0, "assumed": 0}
    assert rollup["total"] == 0


# --- _data_model_rollup ---

def test_mean_min_max_computed_correctly(monkeypatch):
    import generators.confidence_summary as confidence_summary_module

    document = {
        "entities": {
            "Customer": {"fields": {"email": {"confidence": 0.9}, "phone": {"confidence": 0.7}}},
            "Order": {"fields": {"total": {"confidence": 1.0}}},
        }
    }
    monkeypatch.setattr(confidence_summary_module, "build_data_model_document", lambda request: document)

    rollup = _data_model_rollup(_request())

    assert rollup["count"] == 3
    assert rollup["mean_confidence"] == round((0.9 + 0.7 + 1.0) / 3, 2)
    assert rollup["min_confidence"] == 0.7
    assert rollup["max_confidence"] == 1.0


def test_no_fields_rolls_up_to_none_not_a_fabricated_zero(monkeypatch):
    import generators.confidence_summary as confidence_summary_module

    monkeypatch.setattr(confidence_summary_module, "build_data_model_document", lambda request: {"entities": {}})

    rollup = _data_model_rollup(_request())

    assert rollup == {"source_document": "data-model", "count": 0, "mean_confidence": None, "min_confidence": None, "max_confidence": None}


# --- _level_rollup ---

def test_level_counts_match_the_graph():
    earl_document = {"@graph": [{"level": "error"}, {"level": "error"}, {"level": "warning"}]}

    rollup = _level_rollup("usability.earl", earl_document)

    assert rollup == {
        "source_document": "usability.earl",
        "by_level": {"error": 2, "warning": 1, "note": 0, "none": 0},
        "total": 3,
    }


def test_no_findings_rolls_up_to_all_zero_counts():
    rollup = _level_rollup("accessibility.earl", {"@graph": []})

    assert rollup["by_level"] == {"error": 0, "warning": 0, "note": 0, "none": 0}
    assert rollup["total"] == 0


# --- build_confidence_summary ---

def test_every_source_is_present_in_the_assembled_summary(monkeypatch):
    import generators.confidence_summary as confidence_summary_module

    monkeypatch.setattr(confidence_summary_module, "build_requirements_document", lambda request: {"requirements": []})
    monkeypatch.setattr(confidence_summary_module, "build_data_model_document", lambda request: {"entities": {}})
    monkeypatch.setattr(confidence_summary_module, "build_usability_earl_document", lambda request: {"@graph": []})
    monkeypatch.setattr(confidence_summary_module, "build_accessibility_earl_document", lambda request: {"@graph": []})

    summary = build_confidence_summary(_request())

    assert set(summary["sources"]) == {"prd", "data-model", "usability", "accessibility"}
    assert summary["run_id"] == "RUN-1"


def test_the_document_validates_against_its_own_schema(monkeypatch):
    import generators.confidence_summary as confidence_summary_module

    monkeypatch.setattr(confidence_summary_module, "build_requirements_document", lambda request: {"requirements": [_requirement("observed")]})
    monkeypatch.setattr(confidence_summary_module, "build_data_model_document", lambda request: {"entities": {"E": {"fields": {"f": {"confidence": 0.8}}}}})
    monkeypatch.setattr(confidence_summary_module, "build_usability_earl_document", lambda request: {"@graph": [{"level": "warning"}]})
    monkeypatch.setattr(confidence_summary_module, "build_accessibility_earl_document", lambda request: {"@graph": []})

    summary = build_confidence_summary(_request())

    validate_against_schema(summary, _SCHEMA_PATH)


# --- the document ---

def test_generate_returns_a_source_and_a_view_output(monkeypatch):
    import generators.confidence_summary as confidence_summary_module

    monkeypatch.setattr(confidence_summary_module, "build_requirements_document", lambda request: {"requirements": []})
    monkeypatch.setattr(confidence_summary_module, "build_data_model_document", lambda request: {"entities": {}})
    monkeypatch.setattr(confidence_summary_module, "build_usability_earl_document", lambda request: {"@graph": []})
    monkeypatch.setattr(confidence_summary_module, "build_accessibility_earl_document", lambda request: {"@graph": []})

    outputs = ConfidenceSummaryDocument().outputs(_request())

    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]
