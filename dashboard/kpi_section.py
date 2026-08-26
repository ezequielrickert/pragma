"""The landing page's own crawl-wide metrics row (ADR-0016 point 4),
split out of `dashboard/shell.py` once it crossed file-size-audit's WATCH
threshold - a real SRP seam, not a line-count trim: this is "what
numbers does the landing page show and where do they come from," a
different reason to change than `shell.py`'s own job of assembling the
landing/concern/document pages around it.

**Numbers, from the sources that already carry them, never recomputed.**
`pages_finished`/`pages_total`/`components_explored`/`components_total`
come from the caller's own `KpiContext` - `core/docs_engine.py::run()`
already computes these locally (`graph_store.count_visited()`/
`count_unexplored_components()`) for `record_run_manifest`; passing them
through avoids a third, independently-derived copy of the same two
counts. `endpoints_discovered` reads `coverage.json`'s own
`endpoints.observed` field. Requirement confidence, usability, and
accessibility finding totals read `confidence-summary.json`'s own
`sources.{prd,usability,accessibility}` entries (ADR-0029) - never
recomputed from `requirements.json`/the audit documents directly, the
exact duplicate-computation problem ADR-0029 point 2 exists to close.
Any KPI whose source document wasn't produced this run (a document a
config turned off) renders as "not available this run," never a
fabricated zero (ticket #175's own metrics-inventory research).

**Each tile links through to the Graph page**, pre-filtered to its own
real `export.json` node family (`graph.html?family=<Type>`,
`dashboard/graph_assets.py`'s own `initialVisibleIds`) where one exists
(ticket #176, map #172) - "Pages crawled/found" links to `Pantalla`,
"Components" to `Componente`, "Requirements" to `Requisito`, "Endpoints"
to `Endpoint`. Usability/accessibility findings have no populated family
today (`Hallazgo` stays reserved, ADR-0002) - those two tiles show their
real number with no link, rather than one to an empty page.

`source_content`/`source_json` (a document's raw text, or that text
parsed) live here rather than in `shell.py` because they were introduced
for this section's own lookups; `shell.py` reuses the same tiny utility
for one other lookup (`export.json`'s presence, gating the Graph card) -
one shared implementation, not two.

Details: docs/dev/dashboard/kpi_section.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from typing import Any, Dict, Optional, Sequence, Tuple

from core.documents import ProducedDocument


@dataclass(frozen=True)
class KpiContext:
    """The two counts `coverage.json`'s own JSON shape doesn't expose
    (`components_explored`, alongside `pages_finished`) - the caller's
    own already-computed numbers (`core/docs_engine.py::run()`), passed
    through rather than re-derived a third time.
    Details: docs/dev/dashboard/kpi_section.md#kpicontext
    """

    pages_finished: int
    pages_total: int
    components_explored: int
    components_total: int


def source_content(documents: Sequence[Tuple[ProducedDocument, str]], name: str) -> Optional[str]:
    """The raw text of `name`'s own `kind="source"` output, or `None`
    when this run never produced one - a config-disabled or
    degraded-to-off document, not an error.
    Details: docs/dev/dashboard/kpi_section.md#source_content
    """
    for document, content in documents:
        if document.name == name and document.kind == "source":
            return content
    return None


def source_json(documents: Sequence[Tuple[ProducedDocument, str]], name: str) -> Optional[Dict[str, Any]]:
    """`source_content`'s own text, parsed - `None` for a document this
    run never produced, same as `source_content`, plus `None` for one
    that isn't valid JSON.
    Details: docs/dev/dashboard/kpi_section.md#source_json
    """
    content = source_content(documents, name)
    if content is None:
        return None
    try:
        parsed: Dict[str, Any] = json.loads(content)
        return parsed
    except json.JSONDecodeError:
        return None


@dataclass(frozen=True)
class _KpiTile:
    """One landing-page KPI tile's own real display facts, bundled per
    this codebase's own "more than 3 args becomes a dataclass" rule.
    `fraction` drives the radial ring (0..1) - `None` for a metric ADR-0001
    already calls a "saturating count, no denominator" (endpoints, a raw
    findings total) rather than inventing one; the ring then renders
    empty, value-only. `family` is the real `export.json` node `type`
    this metric's own data maps onto - the Graph page already has every
    family's own nodes, so linking through needs nothing invented, only a
    family whose real coverage today (`docs/adr/0002`) actually has one.
    Details: docs/dev/dashboard/kpi_section.md#_kpitile
    """

    label: str
    value: Any  # display value, or None for "not available this run"
    fraction: Optional[float]
    family: Optional[str]


def _kpi_ring(fraction: Optional[float]) -> str:
    if fraction is None:
        return '<div class="ring" style="background:var(--panel-2)"></div>'
    percent = round(max(0.0, min(1.0, fraction)) * 100)
    return (
        f'<div class="ring" style="background:conic-gradient(var(--accent) {percent}%, var(--panel-2) 0)">'
        f'<div class="ring-hole">{percent}%</div></div>'
    )


def _kpi_tile(tile: _KpiTile, graph_available: bool) -> str:
    shown = escape(str(tile.value)) if tile.value is not None else "not available this run"
    body = f'{_kpi_ring(tile.fraction)}<div><div class="value">{shown}</div><div class="label">{escape(tile.label)}</div></div>'
    if tile.family and graph_available:
        return f'<a class="kpi linkable" href="graph.html?family={escape(tile.family)}">{body}</a>'
    return f'<div class="kpi">{body}</div>'


def _safe_fraction(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    """`numerator / denominator`, or `None` when either side is missing or
    the denominator is honestly zero - a ring with nothing to show is not
    a divide-by-zero crash.
    Details: docs/dev/dashboard/kpi_section.md#_safe_fraction
    """
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def kpi_section(
    documents: Sequence[Tuple[ProducedDocument, str]], kpi_context: KpiContext, graph_available: bool
) -> str:
    """The crawl-wide metrics row: pages/components from the caller's own
    counts, endpoints from `coverage.json`, requirement confidence from
    `confidence-summary.json`'s own `prd` entry, usability/accessibility
    finding totals from that same document's own entries - reusing
    what's already real, never recomputing. Each tile links through to
    the Graph page pre-filtered to its own real node family, where one
    exists.
    Details: docs/dev/dashboard/kpi_section.md#kpi_section
    """
    coverage = source_json(documents, "coverage") or {}
    endpoints = coverage.get("endpoints", {}).get("observed")

    confidence = source_json(documents, "confidence-summary") or {}
    prd_confidence = confidence.get("sources", {}).get("prd", {})
    by_confidence = prd_confidence.get("by_confidence")
    # Leads with the real total, not the three-way split - a "12 requirements"
    # headline is legible at a glance in a way "observed 4, inferred 6,
    # assumed 2" packed into one tile's value never was; the split still
    # shows, just as the tile's own secondary label line.
    confidence_total = prd_confidence.get("total")
    confidence_label = (
        ", ".join(f"{category} {count}" for category, count in by_confidence.items()) if by_confidence else None
    )
    observed_fraction = _safe_fraction(by_confidence.get("observed"), confidence_total) if by_confidence else None

    usability_total = confidence.get("sources", {}).get("usability", {}).get("total")
    accessibility_total = confidence.get("sources", {}).get("accessibility", {}).get("total")

    tiles = [
        _KpiTile(
            "Pages crawled / found", f"{kpi_context.pages_finished} / {kpi_context.pages_total}",
            _safe_fraction(kpi_context.pages_finished, kpi_context.pages_total), "Pantalla",
        ),
        _KpiTile(
            "Components interacted / discovered",
            f"{kpi_context.components_explored} / {kpi_context.components_total}",
            _safe_fraction(kpi_context.components_explored, kpi_context.components_total), "Componente",
        ),
        _KpiTile(
            f"Requirements ({confidence_label})" if confidence_label else "Requirements",
            confidence_total, observed_fraction, "Requisito",
        ),
        _KpiTile("Endpoints discovered", endpoints, None, "Endpoint"),
        _KpiTile("Usability findings", usability_total, None, None),
        _KpiTile("Accessibility findings", accessibility_total, None, None),
    ]
    return f'<div class="kpis">{"".join(_kpi_tile(tile, graph_available) for tile in tiles)}</div>'
