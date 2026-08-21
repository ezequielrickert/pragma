"""Unit tests for generators/performance_baseline.py - network latency
percentiles per template_hash, Web Vitals reserved (docs/adr/0026)."""
from core.documents import DocumentRequest
from generators.performance_baseline import (
    PerformanceBaselineDocument,
    _percentile,
    build_performance_baseline,
)
from utils.schema_validation import validate_against_schema

SITE = "perf-test-site"
_SCHEMA_PATH = "schemas/performance-baseline.schema.json"

_ARIA_YAML_A = '- heading "Welcome" [level=1]\n'
_ARIA_YAML_B = '- heading "Different shape" [level=1]\n- list:\n    - listitem "x"\n'


def _snapshot(aria_yaml):
    return {"aria_snapshot_yaml": aria_yaml, "axtree_json": '{"nodes": []}'}


class _Store:
    def __init__(self, snapshots, latency_rows):
        self._snapshots = snapshots
        self._latency_rows = latency_rows

    def get_accessibility_snapshots(self):
        return self._snapshots

    def get_request_latencies_by_page(self):
        return self._latency_rows


def _request(snapshots, latency_rows=()):
    return DocumentRequest(graph_store=_Store(snapshots, latency_rows), site=SITE, agent=None, settings={"run_id": "RUN-1"})


# --- _percentile ---

def test_p50_of_an_odd_length_series_is_the_middle_value():
    assert _percentile([10, 20, 30], 50) == 20.0


def test_p99_of_a_single_value_is_that_value():
    assert _percentile([42], 99) == 42.0


def test_percentiles_are_deterministic_nearest_rank_not_interpolated():
    # 10 values, p95 -> ceil(0.95 * 10) = 10th (last) value.
    values = list(range(1, 11))
    assert _percentile(values, 95) == 10.0


# --- build_performance_baseline ---

def test_two_pages_sharing_a_template_produce_one_entry():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A), "shop/b": _snapshot(_ARIA_YAML_A)}

    entries = build_performance_baseline(_request(snapshots))

    assert len(entries) == 1
    assert len(entries[0]["screens"]) == 2


def test_structurally_different_pages_produce_separate_entries():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A), "shop/b": _snapshot(_ARIA_YAML_B)}

    entries = build_performance_baseline(_request(snapshots))

    assert len(entries) == 2


def test_a_template_with_no_measured_latency_reports_zero_samples_not_omission():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A)}

    entries = build_performance_baseline(_request(snapshots))

    assert entries[0]["network"] == {"sample_count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None}


def test_latency_percentiles_compute_correctly_per_template():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A), "shop/b": _snapshot(_ARIA_YAML_A)}
    latency_rows = [
        {"page_url": "shop/a", "latency_ms": 100},
        {"page_url": "shop/b", "latency_ms": 200},
        {"page_url": "shop/a", "latency_ms": 300},
        {"page_url": "shop/b", "latency_ms": 400},
    ]

    entries = build_performance_baseline(_request(snapshots, latency_rows))

    network = entries[0]["network"]
    assert network["sample_count"] == 4
    assert network["p50_ms"] == _percentile([100, 200, 300, 400], 50)
    assert network["p95_ms"] == _percentile([100, 200, 300, 400], 95)
    assert network["p99_ms"] == _percentile([100, 200, 300, 400], 99)


def test_a_request_on_a_page_with_no_snapshot_is_excluded_not_misattributed():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A)}
    latency_rows = [{"page_url": "shop/unknown-page", "latency_ms": 999}]

    entries = build_performance_baseline(_request(snapshots, latency_rows))

    assert entries[0]["network"]["sample_count"] == 0


def test_web_vitals_are_present_but_null_never_fabricated():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A)}

    entries = build_performance_baseline(_request(snapshots))

    assert entries[0]["web_vitals"] == {"LCP": None, "FCP": None, "CLS": None, "INP": None, "TTFB": None}


def test_no_captured_snapshot_produces_an_empty_baseline_not_an_error():
    assert build_performance_baseline(_request({})) == []


# --- the document ---

def test_generate_returns_a_source_and_a_view_output():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A)}

    outputs = PerformanceBaselineDocument().outputs(_request(snapshots))

    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]


def test_the_document_validates_against_its_own_schema():
    snapshots = {"shop/a": _snapshot(_ARIA_YAML_A)}
    latency_rows = [{"page_url": "shop/a", "latency_ms": 150}]

    entries = build_performance_baseline(_request(snapshots, latency_rows))

    validate_against_schema(entries, _SCHEMA_PATH)
