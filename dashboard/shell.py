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

**The KPI row itself lives in `dashboard/kpi_section.py`**, not here -
split out once it crossed file-size-audit's WATCH threshold, a real SRP
seam ("what numbers does the landing page show" vs. this module's own
job of assembling the landing/concern/document pages around it).
`KpiContext` re-exports from there so `core/docs_engine.py`/`core/engine.py`
(the two real external importers) keep working unchanged.

**A card per concern** (`DOCUMENT_REGISTRY` name, e.g. `"prd"`,
`"openapi"`), each linking to a detail page listing every one of that
concern's own outputs as a card too (ticket #177, map #172 - was a bare
`<ul>`), each in turn linking to its own Phase B render
(`dashboard/renderer_audit.renderer_for` picks generic or Redoc).
`document_context.py`'s own real explanation surfaces on that concern
page directly, before a reviewer opens any specific file.

**A dedicated Graph card** (ticket #163, map #159), alongside the
concern grid rather than inside it - `export.json` rendered as a real
explorable graph (`dashboard/graph_renderer.py`) instead of buried under
the `export` concern's own raw-JSON detail page, which still exists
unchanged. Reads "not available this run" the same way a KPI tile does
when `export.json` wasn't produced.

Details: docs/dev/dashboard/shell.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Dict, List, Sequence, Tuple

from core.documents import ProducedDocument
from utils.io import write_output
from .document_context import render_context_section
from .generic_template import render_generic_page
from .graph_renderer import render_graph_page
from .kpi_section import KpiContext, kpi_section, source_content
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
.kpis { display: flex; flex-wrap: wrap; gap: 14px; margin: 24px 0; }
.kpi { display: flex; align-items: center; gap: 12px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px 16px; min-width: 190px; }
.kpi.linkable { cursor: pointer; }
.kpi.linkable:hover { border-color: var(--accent); }
.kpi .ring { width: 44px; height: 44px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; }
.kpi .ring-hole { width: 32px; height: 32px; border-radius: 50%; background: var(--panel); display: flex; align-items: center; justify-content: center; }
.kpi .value { font-size: 20px; font-weight: 700; }
.kpi .label { color: var(--text-dim); font-size: 11px; margin-top: 2px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; margin-top: 20px; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px; display: block; }
.card:hover { border-color: var(--accent); }
.card .name { font-weight: 600; font-size: 15px; color: var(--text); }
.card .meta { color: var(--text-dim); font-size: 12px; margin-top: 4px; }
.card.unavailable { cursor: default; }
.card.unavailable:hover { border-color: var(--border); }
.badge { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px; font-weight: 600; }
.badge.source { background: var(--accent-dim); color: #b9c9ff; }
.badge.view { background: #2c3a2e; color: var(--ok); }
.badge.rule-catalog, .badge.projection { background: #3a2c1e; color: #fbbf24; }
.context { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.context h2 { margin: 0 0 8px; font-size: 13px; text-transform: uppercase; color: var(--text-dim); }
.context .example { margin: 12px 0 0; padding: 12px; background: var(--panel-2); border-radius: 6px; font-size: 12px; overflow-x: auto; }
"""


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


def _graph_card(available: bool) -> str:
    """The landing page's own top-level Graph card (ticket #163, map
    #159) - alongside the per-concern grid, not inside it, per the
    map's own charting decision (a dedicated card, not buried under the
    `export` concern's own detail page). `export.json` still gets its
    usual concern card too (`renderer_audit.py` never changed) - this is
    an additional, more discoverable way in, not a replacement.
    `available` follows the same "not available this run" posture every
    KPI tile already uses for a document a config turned off, rather
    than a broken link.
    Details: docs/dev/dashboard/shell.md#_graph_card
    """
    if not available:
        return (
            '<div class="card unavailable"><div class="name">Graph</div>'
            '<div class="meta">not available this run</div></div>'
        )
    return (
        '<a class="card" href="graph.html"><div class="name">Graph</div>'
        '<div class="meta">Explore the crawl\'s own graph</div></a>'
    )


def _concern_card(name: str, documents: Sequence[ProducedDocument]) -> str:
    file_word = "file" if len(documents) == 1 else "files"
    return (
        f'<a class="card" href="concern/{escape(name)}.html">'
        f'<div class="name">{escape(documents[0].title)}</div>'
        f'<div class="meta">{len(documents)} {file_word}</div></a>'
    )


def _file_card(document: ProducedDocument) -> str:
    return (
        f'<a class="card" href="../document/{_document_slug(document)}.html">'
        f'<div class="name">{escape(document.filename)}</div>'
        f'<div class="meta"><span class="badge {escape(document.kind)}">{escape(document.kind)}</span></div></a>'
    )


def _concern_page(name: str, documents: Sequence[ProducedDocument], site: str) -> str:
    """The list of one concern's own outputs - a card per file (was a
    bare `<ul>`), with `document_context.py`'s own "what this document is
    typically used for" explanation surfaced here, before a reviewer
    opens any specific file, not only after (ticket #177, map #172).
    Details: docs/dev/dashboard/shell.md#_concern_page
    """
    title = documents[0].title
    cards = "".join(_file_card(document) for document in documents)
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(title)} - {escape(site)}</title>'
        f"<style>{_STYLE}</style></head><body><main>"
        f'<div class="breadcrumb"><a href="../index.html">&larr; {escape(site)}</a></div>'
        f"<h1>{escape(title)}</h1>"
        f'<p>{escape(documents[0].purpose)}</p>'
        f"{render_context_section(documents[0])}"
        f'<div class="grid">{cards}</div>'
        "</main></body></html>\n"
    )


@dataclass(frozen=True)
class _LandingData:
    """The five values `_landing_page` needs, bundled per this codebase's
    own "four-plus arguments become a dataclass" rule (the same one
    `generators/requirements.py::_RequirementFacts` already follows).
    """

    documents: Sequence[Tuple[ProducedDocument, str]]
    concerns: Dict[str, List[ProducedDocument]]
    kpi_context: KpiContext
    site: str
    graph_available: bool


def _landing_page(data: _LandingData) -> str:
    concern_cards = "".join(_concern_card(name, docs) for name, docs in sorted(data.concerns.items()))
    cards = _graph_card(data.graph_available) + concern_cards
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(data.site)} - Pragma Dashboard</title>'
        f"<style>{_STYLE}</style></head><body><main>"
        f"<h1>{escape(data.site)}</h1>"
        f"<p>Generated documentation, one card per concern.</p>"
        f"{kpi_section(data.documents, data.kpi_context, data.graph_available)}"
        f'<div class="grid">{cards}</div>'
        "</main></body></html>\n"
    )


def build_dashboard(
    documents: Sequence[Tuple[ProducedDocument, str]], kpi_context: KpiContext, site: str
) -> Dict[str, str]:
    """`{relative_path: html}` for every page this run's dashboard needs -
    one per-document render, one per concern, the Graph page (when
    `export.json` was produced this run), and the landing page.
    Details: docs/dev/dashboard/shell.md#build_dashboard
    """
    concerns: Dict[str, List[ProducedDocument]] = {}
    for document, _ in documents:
        if document.name == "master":
            continue
        concerns.setdefault(document.name, []).append(document)

    export_content = source_content(documents, "export")
    landing_data = _LandingData(
        documents=documents, concerns=concerns, kpi_context=kpi_context, site=site,
        graph_available=export_content is not None,
    )
    pages: Dict[str, str] = {"dashboard/index.html": _landing_page(landing_data)}
    if export_content is not None:
        pages["dashboard/graph.html"] = render_graph_page(export_content, site)
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
