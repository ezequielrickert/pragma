"""The Phase C dashboard shell (ADR-0016 point 4), ticket #125: the
landing page every other dashboard page is reached from, plus one
per-document render and one per-concern detail page - "Variant C" from
the validated prototype (`prototype/dashboard-80`), the layout that won
the prototype review. No persistent sidebar or top bar: the landing
page carries the navigation, each card drills into its own detail page.

**Pure - returns content, never writes to disk.** `build_dashboard`
takes every produced document's own content (already read by the
caller) and returns `{relative_path: html}` for every page it built -
the same "generator returns content, the pipeline writes it" separation
`core/documents.py::DocumentGenerator` and `dashboard/generic_template.py`
already keep.

**KPI numbers, from the two real sources that already carry them, never
recomputed.** `pages_finished`/`pages_total`/`components_explored`/
`components_total` come from the caller's own `KpiContext` -
`core/docs_engine.py::run()` already computes these locally
(`graph_store.count_visited()`/`count_unexplored_components()`) for
`record_run_manifest`; passing them through avoids a third,
independently-derived copy of the same two counts. `endpoints_discovered`
reads `coverage.json`'s own `endpoints.observed` field - the one number
`coverage.json`'s real JSON shape actually exposes for this. The
requirement-confidence split reads `confidence-summary.json`'s own
`sources.prd.by_confidence` (ADR-0029's own amendment to this ADR) -
`dashboard` never recomputes it from `requirements.json` directly, the
exact duplicate-computation problem ADR-0029 point 2 exists to close.
Any KPI whose source document wasn't produced this run (a document a
config turned off) renders as "not available this run," never a
fabricated zero.

**A card per concern** (`DOCUMENT_REGISTRY` name, e.g. `"prd"`,
`"openapi"`), each linking to a detail page listing every one of that
concern's own outputs, each in turn linking to its own Phase B render
(`dashboard/renderer_audit.renderer_for` picks generic or Redoc).

Details: docs/dev/dashboard/shell.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.documents import ProducedDocument
from utils.io import write_output
from .generic_template import render_generic_page
from .redoc_renderer import render_redoc_page
from .renderer_audit import renderer_for

_STYLE = """
:root {
  --bg: #0f1115; --panel: #161922; --panel-2: #1c2029; --border: #2a2f3a;
  --text: #e4e7ee; --text-dim: #8b93a7; --accent: #5b8cff; --accent-dim: #2c3a5e;
  --ok: #4ade80;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
main { max-width: 1100px; margin: 0 auto; padding: 32px; }
a { color: var(--accent); text-decoration: none; }
h1 { margin: 0 0 4px; }
.breadcrumb { color: var(--text-dim); font-size: 13px; margin-bottom: 20px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 24px 0; }
.kpi { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.kpi .value { font-size: 24px; font-weight: 700; }
.kpi .label { color: var(--text-dim); font-size: 12px; margin-top: 4px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; margin-top: 20px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; display: block; }
.card:hover { border-color: var(--accent); }
.card .name { font-weight: 600; font-size: 15px; color: var(--text); }
.card .meta { color: var(--text-dim); font-size: 12px; margin-top: 4px; }
ul.files { list-style: none; padding: 0; }
ul.files li { padding: 8px 0; border-bottom: 1px solid var(--border); }
.badge { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px; font-weight: 600; margin-left: 8px; }
.badge.source { background: var(--accent-dim); color: #b9c9ff; }
.badge.view { background: #2c3a2e; color: var(--ok); }
.badge.rule-catalog, .badge.projection { background: #3a2c1e; color: #fbbf24; }
"""


@dataclass(frozen=True)
class KpiContext:
    """The two counts `coverage.json`'s own JSON shape doesn't expose
    (`components_explored`, alongside `pages_finished`) - the caller's
    own already-computed numbers (`core/docs_engine.py::run()`), passed
    through rather than re-derived a third time.
    Details: docs/dev/dashboard/shell.md#kpicontext
    """

    pages_finished: int
    pages_total: int
    components_explored: int
    components_total: int


@dataclass(frozen=True)
class DashboardRunContext:
    """Every value `write_dashboard` needs beyond `produced` itself,
    bundled per the same "more than 3 args becomes a dataclass" rule
    `_LandingData` already follows.
    Details: docs/dev/dashboard/shell.md#dashboardruncontext
    """

    kpi_context: KpiContext
    site: str
    out_dir: str


def _source_json(documents: Sequence[Tuple[ProducedDocument, str]], name: str) -> Optional[Dict[str, Any]]:
    """The parsed JSON content of `name`'s own `kind="source"` output, or
    `None` when this run never produced one - a config-disabled or
    degraded-to-off document, not an error.
    Details: docs/dev/dashboard/shell.md#_source_json
    """
    for document, content in documents:
        if document.name == name and document.kind == "source":
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
    return None


def _kpi_tile(label: str, value: Any) -> str:
    shown = escape(str(value)) if value is not None else "not available this run"
    return f'<div class="kpi"><div class="value">{shown}</div><div class="label">{escape(label)}</div></div>'


def _kpi_section(documents: Sequence[Tuple[ProducedDocument, str]], kpi_context: KpiContext) -> str:
    """The crawl-wide metrics row (ADR-0016 point 4): pages/components
    from the caller's own counts, endpoints from `coverage.json`,
    requirement confidence from `confidence-summary.json` - reusing
    what's already real, never recomputing.
    Details: docs/dev/dashboard/shell.md#_kpi_section
    """
    coverage = _source_json(documents, "coverage") or {}
    endpoints = coverage.get("endpoints", {}).get("observed")

    confidence = _source_json(documents, "confidence-summary") or {}
    by_confidence = confidence.get("sources", {}).get("prd", {}).get("by_confidence")
    confidence_label = (
        ", ".join(f"{category} {count}" for category, count in by_confidence.items()) if by_confidence else None
    )

    tiles = [
        _kpi_tile("Pages crawled / found", f"{kpi_context.pages_finished} / {kpi_context.pages_total}"),
        _kpi_tile("Components interacted / discovered", f"{kpi_context.components_explored} / {kpi_context.components_total}"),
        _kpi_tile("Requirement confidence split", confidence_label),
        _kpi_tile("Endpoints discovered", endpoints),
    ]
    return f'<div class="kpis">{"".join(tiles)}</div>'


def _document_slug(document: ProducedDocument) -> str:
    """A stable, always-unique identifier for one produced output's own
    dashboard page - `filename` alone collides for a source/view pair
    sharing one stem (`coverage.json`/`coverage.md`, the same fact
    `master_document.py`'s own format lookup already had to guard
    against); pairing it with `kind` resolves that.
    Details: docs/dev/dashboard/shell.md#_document_slug
    """
    return f"{document.filename}.{document.kind}"


def _render_document_page(document: ProducedDocument, content: str) -> str:
    if renderer_for(document.name) == "redoc":
        return render_redoc_page(document, content)
    return render_generic_page(document, content)


def _concern_card(name: str, documents: Sequence[ProducedDocument]) -> str:
    file_word = "file" if len(documents) == 1 else "files"
    return (
        f'<a class="card" href="concern/{escape(name)}.html">'
        f'<div class="name">{escape(documents[0].title)}</div>'
        f'<div class="meta">{len(documents)} {file_word}</div></a>'
    )


def _concern_page(name: str, documents: Sequence[ProducedDocument], site: str) -> str:
    title = documents[0].title
    items = "".join(
        f'<li><a href="../document/{_document_slug(document)}.html">{escape(document.filename)}</a>'
        f'<span class="badge {escape(document.kind)}">{escape(document.kind)}</span></li>'
        for document in documents
    )
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(title)} - {escape(site)}</title>'
        f"<style>{_STYLE}</style></head><body><main>"
        f'<div class="breadcrumb"><a href="../index.html">&larr; {escape(site)}</a></div>'
        f"<h1>{escape(title)}</h1>"
        f'<p>{escape(documents[0].purpose)}</p>'
        f'<ul class="files">{items}</ul>'
        "</main></body></html>\n"
    )


@dataclass(frozen=True)
class _LandingData:
    """The four values `_landing_page` needs, bundled per this codebase's
    own "four-plus arguments become a dataclass" rule (the same one
    `generators/requirements.py::_RequirementFacts` already follows).
    """

    documents: Sequence[Tuple[ProducedDocument, str]]
    concerns: Dict[str, List[ProducedDocument]]
    kpi_context: KpiContext
    site: str


def _landing_page(data: _LandingData) -> str:
    cards = "".join(_concern_card(name, docs) for name, docs in sorted(data.concerns.items()))
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(data.site)} - Pragma Dashboard</title>'
        f"<style>{_STYLE}</style></head><body><main>"
        f"<h1>{escape(data.site)}</h1>"
        f"<p>Generated documentation, one card per concern.</p>"
        f"{_kpi_section(data.documents, data.kpi_context)}"
        f'<div class="grid">{cards}</div>'
        "</main></body></html>\n"
    )


def build_dashboard(
    documents: Sequence[Tuple[ProducedDocument, str]], kpi_context: KpiContext, site: str
) -> Dict[str, str]:
    """`{relative_path: html}` for every page this run's dashboard needs -
    one per-document render, one per concern, and the landing page.
    Details: docs/dev/dashboard/shell.md#build_dashboard
    """
    concerns: Dict[str, List[ProducedDocument]] = {}
    for document, _ in documents:
        if document.name == "master":
            continue
        concerns.setdefault(document.name, []).append(document)

    landing_data = _LandingData(documents=documents, concerns=concerns, kpi_context=kpi_context, site=site)
    pages: Dict[str, str] = {"dashboard/index.html": _landing_page(landing_data)}
    for name, docs in concerns.items():
        pages[f"dashboard/concern/{name}.html"] = _concern_page(name, docs, site)
    for document, content in documents:
        if document.name == "master":
            continue
        pages[f"dashboard/document/{_document_slug(document)}.html"] = _render_document_page(document, content)
    return pages


def write_dashboard(produced: Sequence[ProducedDocument], context: DashboardRunContext) -> str:
    """Reads every produced document's own content back off disk, calls
    `build_dashboard`, and writes the result - the one impure entry
    point `core/docs_engine.py`/`core/engine.py` call once
    `run_document_pipeline` has already written every file.
    Details: docs/dev/dashboard/shell.md#write_dashboard
    """
    documents = []
    for document in produced:
        with open(document.path, encoding="utf-8") as handle:
            documents.append((document, handle.read()))
    pages = build_dashboard(documents, context.kpi_context, context.site)
    for relative_path, html in pages.items():
        write_output(f"{context.out_dir}/{relative_path}", html)
    return f"{context.out_dir}/dashboard/index.html"
