"""The shared generic template every document without a dedicated
Phase B renderer falls back to (ADR-0016 point 2), ticket #123's
second half. Static HTML, plain Python string formatting - no
templating dependency, matching every other generator in this
pipeline (`generators/*.py` already builds Markdown this way) and
ADR-0016 point 1's own "no web/templating dependencies" constraint.

**Pure - no disk access of its own.** `render_generic_page` takes the
file's content as a string the caller already read, rather than reading
`document.path` itself - the same "generator returns content, the
pipeline writes it" separation `core/documents.py::DocumentGenerator`
already enforces, kept here even though this isn't a `DocumentGenerator`
itself.

**One page, any kind.** Every document's raw content renders inside a
`<pre>` block, HTML-escaped - source, view, rule-catalog, and projection
alike. A kind-specific rendering (syntax highlighting, Markdown-to-HTML)
would be exactly the "per-document renderer" ADR-0016 point 2 reserves
for a dedicated integration that clears its own real bar - the generic
template's whole job is being the honest, uniform fallback, not a worse
copy of what a real renderer would do.

Visual language matches the validated Phase C prototype
(`prototype/dashboard-80`, ADR-0016) - the same dark palette and
kind badges, so Phase B's own pages read as part of the same dashboard
once Phase C's shell wraps them, not a mismatched fallback.

Details: docs/dev/dashboard/generic_template.md#module
"""
from __future__ import annotations

from html import escape

from core.documents import ProducedDocument

_STYLE = """
:root {
  --bg: #0f1115; --panel: #161922; --panel-2: #1c2029; --border: #2a2f3a;
  --text: #e4e7ee; --text-dim: #8b93a7; --accent: #5b8cff; --accent-dim: #2c3a5e;
  --ok: #4ade80; --warn: #fbbf24;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
main { max-width: 1000px; margin: 0 auto; padding: 32px; }
a { color: var(--accent); text-decoration: none; }
h1 { margin: 0 0 4px; font-size: 22px; }
.purpose { color: var(--text-dim); margin: 0 0 20px; }
.badge { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px; font-weight: 600; margin-bottom: 16px; }
.badge.source { background: var(--accent-dim); color: #b9c9ff; }
.badge.view { background: #2c3a2e; color: var(--ok); }
.badge.rule-catalog { background: #3a2c1e; color: var(--warn); }
.badge.projection { background: #3a2c1e; color: var(--warn); }
pre { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 20px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
"""


def render_generic_page(document: ProducedDocument, content: str) -> str:
    """One self-contained static HTML page for `document` - `content` is
    the raw text of the file it describes, already read by the caller.
    Details: docs/dev/dashboard/generic_template.md#render_generic_page
    """
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(document.title)}</title>'
        f"<style>{_STYLE}</style></head><body><main>"
        f"<h1>{escape(document.title)}</h1>"
        f'<p class="purpose">{escape(document.purpose)}</p>'
        f'<span class="badge {escape(document.kind)}">{escape(document.kind)}</span>'
        f"<pre>{escape(content)}</pre>"
        "</main></body></html>\n"
    )
