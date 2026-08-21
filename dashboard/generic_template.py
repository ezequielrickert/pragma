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

**One page, any kind - except Markdown, which is the majority of it.**
Every non-Markdown document's raw content still renders inside a `<pre>`
block, HTML-escaped: syntax highlighting for CALM/CycloneDX/SARIF/etc.
would be exactly the "per-document renderer" ADR-0016 point 2 reserves
for a dedicated integration that clears its own real bar, and staying a
uniform fallback for those formats is still the honest choice.

**Update - ticket #144 (map #142)**: Markdown is a different case from
those - it's nearly every `view`/`projection` document this pipeline
produces (`prd.md`, `catalog.md`, `tokens.md`, `decisions.adr/*.md`,
...), not a rare exotic format with no good renderer, so leaving it in
the generic `<pre>` fallback showed a reviewer raw `#`/`>`/`| --- |`
syntax instead of the prose/tables it was meant to be. `_render_markdown`
converts it to real HTML (`markdown`, `tables`/`fenced_code` extensions -
GFM-style tables and code fences are what this pipeline's own Markdown
generators actually emit) for any document whose `path` ends in `.md`,
regardless of `kind` - `master_document.py`'s own `llms.txt` is `kind=
"view"` too but not Markdown, so the extension is the real signal here,
not the kind.

**Sanitized, not trusted.** Python-Markdown passes raw embedded HTML
straight through by design (its own FAQ says so) - and every document
here ultimately traces back to text scraped off a crawled site, which
this project treats as untrusted input everywhere else. A component's
own `text` narrated into `prd.md`/`catalog.md` containing a real
`<script>` tag would otherwise execute in whoever's browser opens this
dashboard. `bleach.clean()` strips anything outside `_ALLOWED_TAGS`/
`_ALLOWED_ATTRIBUTES` (a plain-Python sanitizer, no native wheel - this
project already has one recurring native-dependency pain point, see
`ladybug`'s own C API gap, not worth a second one here) after Markdown
conversion, keeping only the structural tags these generators actually
emit.

Visual language matches the validated Phase C prototype
(`prototype/dashboard-80`, ADR-0016) - the same dark palette and
kind badges, so Phase B's own pages read as part of the same dashboard
once Phase C's shell wraps them, not a mismatched fallback.

Details: docs/dev/dashboard/generic_template.md#module
"""
from __future__ import annotations

from html import escape

import bleach
import markdown

from core.documents import ProducedDocument
from .document_context import render_context_section

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
.breadcrumb { color: var(--text-dim); font-size: 13px; margin-bottom: 20px; }
.purpose { color: var(--text-dim); margin: 0 0 20px; }
.badge { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 999px; font-weight: 600; margin-bottom: 16px; }
.badge.source { background: var(--accent-dim); color: #b9c9ff; }
.badge.view { background: #2c3a2e; color: var(--ok); }
.badge.rule-catalog { background: #3a2c1e; color: var(--warn); }
.badge.projection { background: #3a2c1e; color: var(--warn); }
pre { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 20px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
.markdown-body table { border-collapse: collapse; width: 100%; margin: 16px 0; }
.markdown-body th, .markdown-body td { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
.markdown-body th { background: var(--panel-2); }
.markdown-body code { background: var(--panel-2); padding: 1px 5px; border-radius: 4px; font-size: 13px; }
.markdown-body pre code { background: none; padding: 0; }
.markdown-body blockquote { border-left: 3px solid var(--border); margin: 0; padding-left: 14px; color: var(--text-dim); }
.context { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.context h2 { margin: 0 0 8px; font-size: 13px; text-transform: uppercase; color: var(--text-dim); }
.context .example { margin: 12px 0 0; padding: 12px; background: var(--panel-2); border-radius: 6px; font-size: 12px; overflow-x: auto; }
"""

# GFM-style tables and code fences - what this pipeline's own Markdown
# generators (generators/*.py, docstrings above) actually emit.
_MARKDOWN_EXTENSIONS = ["tables", "fenced_code"]

# Every structural tag Markdown-conversion above can actually produce
# from this pipeline's own generators - nothing script/style/event-
# handler-capable makes this list, regardless of what a scraped site's
# own text tried to smuggle in.
_ALLOWED_TAGS = [
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "b", "i", "ul", "ol", "li", "blockquote",
    "code", "pre", "table", "thead", "tbody", "tr", "th", "td", "a",
]
_ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}


def _is_markdown(document: ProducedDocument) -> bool:
    """The extension, not `kind`, is the real signal - `llms.txt`
    (`master_document.py`) is `kind="view"` too but isn't Markdown.
    Details: docs/dev/dashboard/generic_template.md#_is_markdown
    """
    return document.path.endswith(".md")


def _render_markdown(content: str) -> str:
    """Markdown-to-HTML, then sanitized - see the module docstring's
    own "Sanitized, not trusted" section for why the second step isn't
    optional here.
    Details: docs/dev/dashboard/generic_template.md#_render_markdown
    """
    html = markdown.markdown(content, extensions=_MARKDOWN_EXTENSIONS)
    return bleach.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRIBUTES, strip=True)


def render_generic_page(document: ProducedDocument, content: str) -> str:
    """One self-contained static HTML page for `document` - `content` is
    the raw text of the file it describes, already read by the caller.
    The breadcrumb link back to the document's own concern page uses
    `document.name`/`.title` directly - the same pair `dashboard/shell.py`
    groups documents by concern with, so no second lookup is needed.
    Details: docs/dev/dashboard/generic_template.md#render_generic_page
    """
    body = (
        f'<div class="markdown-body">{_render_markdown(content)}</div>'
        if _is_markdown(document)
        else f"<pre>{escape(content)}</pre>"
    )
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(document.title)}</title>'
        f"<style>{_STYLE}</style></head><body><main>"
        f'<div class="breadcrumb"><a href="../concern/{escape(document.name)}.html">'
        f"&larr; {escape(document.title)}</a></div>"
        f"<h1>{escape(document.title)}</h1>"
        f'<p class="purpose">{escape(document.purpose)}</p>'
        f'<span class="badge {escape(document.kind)}">{escape(document.kind)}</span>'
        f"{render_context_section(document)}"
        f"{body}"
        "</main></body></html>\n"
    )
