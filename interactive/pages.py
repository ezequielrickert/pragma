"""Every page `interactive/server.py`'s routes render, split out once
that file crossed `file-size-audit`'s own 300-line WATCH threshold
(ticket #154) - a real, identifiable seam between "how a page looks"
and "how the server runs" (routing, threading, shutdown), the same
"rendering lives in its own file" precedent `dashboard/generic_
template.py`/`dashboard/redoc_renderer.py` already set for the static
dashboard. Plain Python string building, no Jinja templates - matching
that same precedent, not a second convention.

Most functions here are pure - no disk access, no Flask app object;
`url_for()` is the one Flask dependency, and it works identically
regardless of which module calls it, as long as an app/request context
is active (always true for a route handler). `color_token_form` and
`generic_form_panel` are the two exceptions - each reads through its
own data module's accessor (`token_form.color_tokens`,
`generic_form.form_entries`) to know what to render, the same way a
route handler would, just one call removed from it.

**View/edit split** (ticket #178): every document opens in a read-only
view by default (`document_view_page`) - the same rendered output the
static dashboard already produces for that file type. An "Edit" link
leads to the diff-gutter editor on a separate `/edit` sub-route
(`document_page`). `document_view_page`'s renderer dispatch is the
same three cases `dashboard/generic_template.py` + `dashboard/
redoc_renderer.py` already use: Markdown → `render_markdown`,
`openapi` → `render_redoc_embed`, everything else → `<pre>`.

Details: docs/dev/interactive/pages.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from typing import Dict, List, Optional

import jsonschema
from flask import url_for

from dashboard.generic_template import render_markdown
from dashboard.redoc_renderer import render_redoc_embed

from .customization import DocumentRef, SiteOutput, available_documents, schema_path_for
from .generic_form import ENTRY_FIELD_PREFIX, FormEntry, FormField, Widget, form_entries, has_generic_form
from .token_form import color_tokens

COLOR_FIELD_PREFIX = "token:"

STYLE = """
:root {
  --bg: #0f1115; --panel: #161922; --border: #2a2f3a;
  --text: #e4e7ee; --text-dim: #8b93a7; --accent: #5b8cff; --danger: #f87171;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 -apple-system, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }
main { max-width: 900px; margin: 0 auto; padding: 32px; }
a { color: var(--accent); text-decoration: none; }
h1 { font-size: 20px; }
ul.documents { list-style: none; padding: 0; }
ul.documents li { padding: 6px 0; border-bottom: 1px solid var(--border); }
textarea { width: 100%; min-height: 400px; background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 13px; }
.error { background: #3a1e1e; border: 1px solid var(--danger); color: var(--danger);
  padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; white-space: pre-wrap; }
button { background: var(--accent); color: white; border: none; border-radius: 6px;
  padding: 8px 18px; font-size: 14px; cursor: pointer; }
.finalizar { background: var(--danger); }
.view-actions { margin-bottom: 16px; }
.view-actions a.edit-link { display: inline-block; background: var(--accent); color: white;
  border-radius: 6px; padding: 8px 18px; font-size: 14px; }
.view-body { margin-top: 8px; }
.view-body pre { background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 20px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
.view-body .markdown-body { line-height: 1.7; }
.view-body .markdown-body table { border-collapse: collapse; width: 100%; margin: 16px 0; }
.view-body .markdown-body th, .view-body .markdown-body td { border: 1px solid var(--border);
  padding: 6px 10px; text-align: left; }
.view-body .markdown-body th { background: var(--panel); }
.view-body .markdown-body code { background: var(--panel); padding: 1px 5px; border-radius: 4px;
  font-size: 13px; }
.view-body .markdown-body pre code { background: none; padding: 0; }
.view-body .markdown-body blockquote { border-left: 3px solid var(--border); margin: 0;
  padding-left: 14px; color: var(--text-dim); }
.chat { margin-top: 24px; border-top: 1px solid var(--border); padding-top: 16px; }
.chat .turn { padding: 8px 12px; border-radius: 6px; margin-bottom: 8px; }
.chat .turn.user { background: var(--panel); }
.chat .turn.assistant { background: var(--accent-dim, #1c2438); }
.chat .role { color: var(--text-dim); font-size: 11px; text-transform: uppercase; }
.chat .chat-error { color: var(--danger); }
.chat input[type="text"] { width: 75%; background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; }
.color-tokens { margin-bottom: 24px; border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.color-tokens .row { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.color-tokens .row label { flex: 1; font-family: monospace; font-size: 13px; }
.color-tokens input[type="color"] { width: 48px; height: 28px; border: 1px solid var(--border);
  border-radius: 4px; background: none; padding: 0; cursor: pointer; }
.generic-form { margin-bottom: 24px; }
.generic-form fieldset { border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px;
  margin-bottom: 12px; }
.generic-form legend { color: var(--text-dim); font-size: 12px; padding: 0 6px; }
.generic-form .row { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.generic-form .row label { width: 140px; flex-shrink: 0; font-family: monospace; font-size: 13px; }
.generic-form select, .generic-form input[type="text"] { flex: 1; background: var(--panel);
  color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; }
.generic-form textarea { flex: 1; min-height: 60px; background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-family: inherit; }
.diff-panes { display: flex; gap: 16px; margin-bottom: 12px; }
.diff-panes .pane { flex: 1; min-width: 0; }
.diff-panes .gutter-row { display: flex; }
.diff-panes .gutter { width: 28px; margin: 0; padding: 12px 4px; text-align: right;
  background: var(--panel); border: 1px solid var(--border); border-right: none;
  color: var(--text-dim); overflow: hidden; font-family: monospace; font-size: 13px; }
.diff-panes .pane-content, .diff-panes textarea { flex: 1; min-width: 0; margin: 0; padding: 12px;
  max-height: 400px; overflow: auto; background: var(--panel); color: var(--text);
  border: 1px solid var(--border); border-radius: 0 6px 6px 0; font-family: monospace;
  font-size: 13px; white-space: pre-wrap; }
"""

_DIFF_GUTTER_JS = """
function diffLines(a, b) {
  const av = a.split("\\n"), bv = b.split("\\n");
  const n = av.length, m = bv.length;
  const lcs = Array.from({length: n + 1}, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      lcs[i][j] = av[i] === bv[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const rows = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (av[i] === bv[j]) { rows.push("same"); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { rows.push("del"); i++; }
    else { rows.push("add"); j++; }
  }
  while (i < n) { rows.push("del"); i++; }
  while (j < m) { rows.push("add"); j++; }
  return rows;
}
function paintGutters(errorLine) {
  const current = document.getElementById("edit-content").value;
  const rows = diffLines(ORIGINAL_CONTENT, current);
  const origMarks = [], curMarks = [];
  let curLineNo = 0;
  for (const row of rows) {
    if (row !== "add") { origMarks.push(row === "del" ? "\\u2022" : "\\u00a0"); }
    if (row !== "del") {
      curLineNo++;
      curMarks.push(curLineNo === errorLine ? "!" : (row === "add" ? "\\u2022" : "\\u00a0"));
    }
  }
  document.getElementById("orig-gutter").textContent = origMarks.join("\\n");
  document.getElementById("cur-gutter").textContent = curMarks.join("\\n");
  syncGutters();
}
function syncGutters() {
  document.getElementById("orig-gutter").scrollTop = document.getElementById("orig-pane").scrollTop;
  document.getElementById("cur-gutter").scrollTop = document.getElementById("edit-content").scrollTop;
}
"""


def page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{STYLE}</style></head><body><main>{body}</main></body></html>\n"
    )


def landing_page(where: SiteOutput) -> str:
    items = "".join(
        f'<li><a href="{url_for("view_document", filename=ref.filename, extension=ref.extension)}">'
        f"{escape(ref.filename)}.{escape(ref.extension)}</a></li>"
        for ref in available_documents(where)
    )
    return (
        f"<h1>{escape(where.site)}</h1>"
        '<div style="margin-bottom: 24px; padding: 12px; background: #1a202c; border: 1px solid #2d3748; border-radius: 6px;">'
        '<a href="/graph" style="font-weight: bold; color: #63b3ed; text-decoration: none;">'
        '🔍 Launch Graph Explorer (Live Kùzu Database Mode)</a>'
        '</div>'
        '<p>Every document this crawl produced. Open one to read it; click Edit to customise '
        "it - edits write a separate copy and never touch the original crawl output.</p>"
        f'<ul class="documents">{items}</ul>'
        '<form method="post" action="/finalizar" onsubmit="return confirm(\'Finalizar sesión?\')">'
        '<button class="finalizar" type="submit">Finalizar</button></form>'
    )


@dataclass(frozen=True)
class ValidationFailure:
    """A failed save's message plus the real jsonschema data path
    (`exc.absolute_path`, never a source line number) - `document_page`'s
    own diff gutter turns that path into an approximate line marker
    (ticket #155), not just a plain-text banner.
    Details: docs/dev/interactive/pages.md#validationfailure
    """

    message: str
    path: List[str]


@dataclass(frozen=True)
class DocumentEditState:
    """Everything `document_page` needs for one edit session - `content`
    and `original` bundled per python-clean-code's F1 (max 3 args),
    matching `SiteOutput`/`DocumentRef`'s own precedent.
    Details: docs/dev/interactive/pages.md#documenteditstate
    """

    content: str
    original: str
    failure: Optional[ValidationFailure]


@dataclass(frozen=True)
class DocumentViewState:
    """Everything `document_view_page` needs to render - `content` and optional
    `original` (diff source) bundled to maintain python-clean-code's F1 limit
    of max 3 args.
    Details: docs/dev/interactive/pages.md#documentviewstate
    """

    content: str
    original: Optional[str] = None


def validation_error_message(exc: Exception) -> str:
    if isinstance(exc, jsonschema.ValidationError):
        return f"Schema validation failed at {list(exc.absolute_path) or '(root)'}: {exc.message}"
    return f"Could not parse this document: {exc}"


def _approximate_line_for_path(content: str, path: List[str]) -> Optional[int]:
    """The best guess at which line of `content` a jsonschema error's
    data `path` corresponds to - the last segment that looks like a
    real key, searched as a quoted JSON string. `None` when nothing
    matches, or the match is ambiguous (more than one line contains
    it) - a wrong guess is worse than an honest "can't point at a line"
    here.
    Details: docs/dev/interactive/pages.md#_approximate_line_for_path
    """
    for segment in reversed(path):
        needle = f'"{segment}"'
        hits = [n for n, line in enumerate(content.splitlines(), start=1) if needle in line]
        if len(hits) == 1:
            return hits[0]
    return None


def document_view_page(ref: DocumentRef, state: DocumentViewState, renderer: str) -> str:
    """The read-only view for `ref` - the default surface when opening a
    document (ticket #178). `renderer` is the verdict from
    `dashboard.renderer_audit.renderer_for`, the same three cases the
    static dashboard already dispatches on: `"redoc"` for `openapi`,
    `"generic"` for everything else (Markdown rendered to HTML, raw
    content in a `<pre>` for all other extensions).
    If `state.original` is provided (ticket #181), it renders a two-column side-by-side
    comparison of original and content (customized/current).
    Details: docs/dev/interactive/pages.md#document_view_page
    """
    edit_url = url_for("edit_document", filename=ref.filename, extension=ref.extension)

    def _render_body(text: str, suffix: str = "") -> str:
        if renderer == "redoc":
            return render_redoc_embed(text, suffix=suffix)
        elif ref.extension == "md":
            return f'<div class="markdown-body">{render_markdown(text)}</div>'
        else:
            return f"<pre>{escape(text)}</pre>"

    if state.original is not None:
        body = (
            '<div class="diff-panes">'
            '<div class="pane"><h3>Original</h3>'
            f'<div class="view-body">{_render_body(state.original, suffix="-orig")}</div>'
            '</div>'
            '<div class="pane"><h3>Current</h3>'
            f'<div class="view-body">{_render_body(state.content, suffix="-curr")}</div>'
            '</div>'
            '</div>'
        )
    else:
        body = f'<div class="view-body">{_render_body(state.content)}</div>'

    return (
        f'<p><a href="{url_for("index")}">\u2190 Back</a></p>'
        f"<h1>{escape(ref.filename)}.{escape(ref.extension)}</h1>"
        f'<div class="view-actions"><a class="edit-link" href="{edit_url}">Edit</a></div>'
        f"{body}"
    )


def document_page(ref: DocumentRef, state: DocumentEditState) -> str:
    error_html = f'<div class="error">{escape(state.failure.message)}</div>' if state.failure else ""
    error_line = _approximate_line_for_path(state.content, state.failure.path) if state.failure else None
    schema_note = (
        f"Validated against {escape(schema_path_for(ref.filename))} on save."
        if schema_path_for(ref.filename)
        else "No schema known for this document - saved as-is, unvalidated."
    )
    view_url = url_for("view_document", filename=ref.filename, extension=ref.extension)
    return (
        f'<p><a href="{view_url}">\u2190 {escape(ref.filename)}.{escape(ref.extension)}</a></p>'
        f"<h1>{escape(ref.filename)}.{escape(ref.extension)}</h1>"
        f"<p>{schema_note}</p>"
        f"{error_html}"
        '<div class="diff-panes">'
        '<div class="pane"><h3>Original</h3><div class="gutter-row">'
        '<pre id="orig-gutter" class="gutter"></pre>'
        f'<pre id="orig-pane" class="pane-content" onscroll="syncGutters()">{escape(state.original)}</pre>'
        "</div></div>"
        '<div class="pane"><h3>Current</h3>'
        '<form method="post"><div class="gutter-row">'
        '<pre id="cur-gutter" class="gutter"></pre>'
        f'<textarea id="edit-content" name="content" oninput="paintGutters({error_line or "null"})" '
        f'onscroll="syncGutters()">{escape(state.content)}</textarea>'
        "</div>"
        '<button type="submit">Save</button></form>'
        "</div></div>"
        f"<script>const ORIGINAL_CONTENT = {json.dumps(state.original)};{_DIFF_GUTTER_JS}"
        f"paintGutters({error_line or 'null'});</script>"
    )


def _chat_turn_html(turn: Dict[str, str]) -> str:
    role = turn["role"]
    return f'<div class="turn {escape(role)}"><div class="role">{escape(role)}</div>{escape(turn["content"])}</div>'


def chat_panel(ref: DocumentRef, history: List[Dict[str, str]], chat_error: Optional[str]) -> str:
    """The chat panel on a document's own edit page (ticket #153) -
    every turn so far, then an input for the next one. `chat_error` is
    the local model's own failure (e.g. the server is unreachable), not
    a grounding gap - `grounding_for`'s own `[]` renders as a real
    `system_instruction` line ("no real dependency data"), never as an
    error here.
    Details: docs/dev/interactive/pages.md#chat_panel
    """
    turns_html = "".join(_chat_turn_html(turn) for turn in history) or "<p>No messages yet.</p>"
    error_html = f'<p class="chat-error">{escape(chat_error)}</p>' if chat_error else ""
    return (
        '<div class="chat"><h2>Chat</h2>'
        f"{turns_html}{error_html}"
        f'<form method="post" action="{url_for("chat", filename=ref.filename, extension=ref.extension)}">'
        '<input type="text" name="message" placeholder="Ask about this change..." required>'
        '<button type="submit">Send</button>'
        "</form></div>"
    )


def color_token_form(where: SiteOutput) -> str:
    """The `core.color.*` picker section on `tokens.json`'s own edit
    page (ticket #154) - `""` when this site's `tokens.json` has no
    color tokens at all, so an empty section doesn't render for nothing.
    Form fields are named `token:<token_id>` - `server.py::save_colors`
    strips that same prefix back off to know which token each value
    belongs to.
    Details: docs/dev/interactive/pages.md#color_token_form
    """
    tokens = color_tokens(where)
    if not tokens:
        return ""
    rows = "".join(
        f'<div class="row"><label for="{escape(token_id)}">{escape(token_id)}</label>'
        f'<input type="color" id="{escape(token_id)}" name="{COLOR_FIELD_PREFIX}{escape(token_id)}" '
        f'value="{escape(value)}"></div>'
        for token_id, value in sorted(tokens.items())
    )
    return (
        '<div class="color-tokens"><h2>Color tokens</h2>'
        f'<form method="post" action="{url_for("save_colors")}">'
        f"{rows}"
        '<button type="submit">Save colors</button>'
        "</form></div>"
    )


def _generic_field_html(index: int, field: FormField) -> str:
    field_id = f"{ENTRY_FIELD_PREFIX}{index}:{field.name}"
    if field.widget is Widget.SELECT:
        input_html = f'<select id="{field_id}" name="{field_id}">' + "".join(
            f'<option value="{escape(option)}"{" selected" if option == field.value else ""}>{escape(option)}</option>'
            for option in field.options
        ) + "</select>"
    elif field.widget is Widget.TEXTAREA:
        input_html = f'<textarea id="{field_id}" name="{field_id}">{escape(field.value)}</textarea>'
    else:
        input_html = f'<input type="text" id="{field_id}" name="{field_id}" value="{escape(field.value)}">'
    return f'<div class="row"><label for="{field_id}">{escape(field.name)}</label>{input_html}</div>'


def _generic_entry_html(entry: FormEntry) -> str:
    fields_html = "".join(_generic_field_html(entry.index, field) for field in entry.fields)
    return f"<fieldset><legend>{escape(entry.summary)}</legend>{fields_html}</fieldset>"


def generic_form_panel(where: SiteOutput, ref: DocumentRef) -> str:
    """ADR-0034's generic form - one `<fieldset>` per row of `ref`'s
    array, one real input per HITL-fillable field (widget resolved
    against `ref`'s own schema, never hand-picked here). `""` when
    `ref` has no `GenericFormSpec` at all, or this site never produced
    it - the raw-text editor is the only path either way, same as
    `color_token_form`'s own empty case.
    Details: docs/dev/interactive/pages.md#generic_form_panel
    """
    if not has_generic_form(ref.filename):
        return ""
    entries = form_entries(where, ref)
    if not entries:
        return ""
    rows = "".join(_generic_entry_html(entry) for entry in entries)
    return (
        '<div class="generic-form"><h2>Review</h2>'
        f'<form method="post" action="{url_for("save_fields", filename=ref.filename, extension=ref.extension)}">'
        f"{rows}"
        '<button type="submit">Save</button>'
        "</form></div>"
    )
