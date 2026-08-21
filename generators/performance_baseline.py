"""`performance-baseline.json` - network latency aggregates per distinct
`template_hash`, Core Web Vitals reserved, docs/adr/0026.

**Real vs. reserved** (point 1). Network-level latency (`Request.latency_ms`,
captured by every crawl already) ships as real p50/p95/p99 aggregates.
Core Web Vitals (LCP, FCP, CLS, INP, TTFB) need Playwright's Performance
API/CDP wired to capture them - not built here, present as typed `null`
fields until a future ticket instruments it, the same reserved-field
posture `coverage` (ADR-0001) and `risk-register` (ADR-0024) already
established for real-but-uninstrumented data.

**Per template, not per screen** (point 2). Baselines group by
`tree`'s own `template_hash` (`aria_tree.template_hash_by_page`,
ADR-0003) - near-identical pages sharing a template have near-identical
performance characteristics, and measuring every `SCR-<hash>` instance
independently would be redundant. Every screen with a captured
accessibility snapshot gets a template entry regardless of whether any
of its requests carry a measured latency; `network.sample_count` says
honestly when it's zero rather than the template being silently absent.

**Format: pragma-native, Web Vitals' own metric names where they apply**
(point 3). Not Lighthouse CI's bundled report - that would reintroduce
the accessibility/SEO/best-practices overlap this map has avoided
everywhere else. `web_vitals` uses the metrics' own authoritative
names; `network` is a pragma-specific aggregate Web Vitals has no
equivalent for.

Details: docs/dev/generators/performance_baseline.md#module
"""
from __future__ import annotations

import json
from math import ceil
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from .aria_tree import template_hash_by_page

_SCHEMA_PATH = "schemas/performance-baseline.schema.json"

# Web Vitals' own metric names (ADR-0026 point 3) - present, typed null,
# until a future ticket wires Playwright's Performance API/CDP capture.
_RESERVED_WEB_VITALS: Dict[str, Any] = {"LCP": None, "FCP": None, "CLS": None, "INP": None, "TTFB": None}


def _screen_id(page_url: str) -> str:
    return f"SCR-{short_hash(page_url)}"


def _percentile(values: Sequence[int], percentile: float) -> float:
    """Nearest-rank percentile - no interpolation, so p50/p95/p99 are the
    same number regardless of which statistics library or Python version
    computed them, matching this pipeline's own determinism guarantee.
    Details: docs/dev/generators/performance_baseline.md#_percentile
    """
    ordered = sorted(values)
    rank = max(1, ceil(percentile / 100 * len(ordered)))
    return float(ordered[rank - 1])


def _network_aggregate(latencies: List[int]) -> Dict[str, Any]:
    """`sample_count` plus p50/p95/p99, or all three `null` when this
    template has no measured latency yet - never a fabricated 0.
    Details: docs/dev/generators/performance_baseline.md#_network_aggregate
    """
    if not latencies:
        return {"sample_count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None}
    return {
        "sample_count": len(latencies),
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
    }


def _group_by_template(template_by_page: Dict[str, str]) -> Dict[str, List[str]]:
    """`{template_hash: [SCR-<hash>, ...]}`, sorted - every screen sharing
    one structural template, grouped for the caller to attribute
    latencies to.
    Details: docs/dev/generators/performance_baseline.md#_group_by_template
    """
    screens_by_template: Dict[str, List[str]] = {}
    for page_url, template_hash in template_by_page.items():
        screens_by_template.setdefault(template_hash, []).append(_screen_id(page_url))
    return {template_hash: sorted(screens) for template_hash, screens in screens_by_template.items()}


def _latencies_by_template(
    template_by_page: Dict[str, str], latency_rows: List[Dict[str, Any]]
) -> Dict[str, List[int]]:
    """Every measured `Request.latency_ms`, attributed to the template of
    the page it was observed on - a request on a page with no captured
    accessibility snapshot (so no known template) contributes nothing,
    since there is no template to attribute it to.
    Details: docs/dev/generators/performance_baseline.md#_latencies_by_template
    """
    latencies: Dict[str, List[int]] = {}
    for row in latency_rows:
        template_hash = template_by_page.get(row["page_url"])
        if template_hash is not None:
            latencies.setdefault(template_hash, []).append(row["latency_ms"])
    return latencies


def build_performance_baseline(request: DocumentRequest) -> List[Dict[str, Any]]:
    """One entry per distinct `template_hash` this crawl observed, its
    network-latency samples aggregated across every screen sharing that
    template.
    Details: docs/dev/generators/performance_baseline.md#build_performance_baseline
    """
    template_by_page = template_hash_by_page(request)
    screens_by_template = _group_by_template(template_by_page)
    latencies_by_template = _latencies_by_template(template_by_page, request.graph_store.get_request_latencies_by_page())

    return [
        {
            "template_hash": template_hash,
            "screens": screens_by_template[template_hash],
            "network": _network_aggregate(latencies_by_template.get(template_hash, [])),
            "web_vitals": dict(_RESERVED_WEB_VITALS),
        }
        for template_hash in sorted(screens_by_template)
    ]


def _render_performance_baseline_view(entries: List[Dict[str, Any]]) -> str:
    """`performance-baseline.md` - mechanically rendered from
    `performance-baseline.json`, never hand-authored in parallel with it.
    Details: docs/dev/generators/performance_baseline.md#_render_performance_baseline_view
    """
    lines = ["# Performance Baseline", ""]
    if not entries:
        lines.append("No page in this crawl carried a captured accessibility snapshot to group by template.")
        return "\n".join(lines) + "\n"

    lines += [
        "Network latency, aggregated per structural template (docs/adr/0003's `template_hash`) rather "
        "than per screen. Core Web Vitals are reserved - present as `null` until a future capture pass "
        "wires Playwright's Performance API.",
        "",
        "| Template | Screens | Samples | p50 (ms) | p95 (ms) | p99 (ms) |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {entry['template_hash']} | {len(entry['screens'])} | {entry['network']['sample_count']} | "
        f"{entry['network']['p50_ms'] if entry['network']['p50_ms'] is not None else '-'} | "
        f"{entry['network']['p95_ms'] if entry['network']['p95_ms'] is not None else '-'} | "
        f"{entry['network']['p99_ms'] if entry['network']['p99_ms'] is not None else '-'} |"
        for entry in entries
    ]
    lines.append("")
    return "\n".join(lines)


def _as_json(entries: List[Dict[str, Any]]) -> str:
    return json.dumps(entries, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("performance-baseline")
class PerformanceBaselineDocument(DocumentGenerator):
    """`performance-baseline.json` (source, schema-validated) and
    `performance-baseline.md` (view) - docs/adr/0026.
    Details: docs/dev/generators/performance_baseline.md#performancebaselinedocument
    """

    name = "performance-baseline"
    title = "Performance Baseline"
    purpose = "Network latency percentiles per structural template, with Core Web Vitals reserved for a future capture pass."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        entries = build_performance_baseline(request)
        validate_against_schema(entries, _SCHEMA_PATH)
        view = _render_performance_baseline_view(entries)
        return (
            DocumentOutput(filename="performance-baseline", kind="source", extension="json", content=_as_json(entries)),
            DocumentOutput(filename="performance-baseline", kind="view", extension="md", content=view),
        )
