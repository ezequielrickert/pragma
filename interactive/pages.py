"""Every page `interactive/server.py`'s routes render, split out once
that file crossed `file-size-audit`'s own 300-line WATCH threshold
(ticket #154) - a real, identifiable seam between "how a page looks"
and "how the server runs" (routing, threading, shutdown), the same
"rendering lives in its own file" precedent `dashboard/generic_
template.py`/`dashboard/redoc_renderer.py` already set for the static
dashboard. Plain Python string building, no Jinja templates - matching
that same precedent, not a second convention.

Every function here is pure - no disk access, no Flask app object -
`url_for()` is the one Flask dependency, and it works identically
regardless of which module calls it, as long as an app/request context
is active (always true for a route handler).

Details: docs/dev/interactive/pages.md#module
"""
from __future__ import annotations

from html import escape
from typing import Dict, List, Optional

import jsonschema
from flask import url_for

from .customization import DocumentRef, SiteOutput, available_documents, schema_path_for
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
"""


def page(title: str, body: str) -> str:
    return (
        "<!doctype html>\n"
        f'<html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>'
        f"<style>{STYLE}</style></head><body><main>{body}</main></body></html>\n"
    )


def landing_page(where: SiteOutput) -> str:
    items = "".join(
        f'<li><a href="{url_for("edit_document", filename=ref.filename, extension=ref.extension)}">'
        f"{escape(ref.filename)}.{escape(ref.extension)}</a></li>"
        for ref in available_documents(where)
    )
    return (
        f"<h1>{escape(where.site)}</h1>"
        '<p>Every document this crawl produced, editable below. Editing writes a customized '
        "copy - the original crawl output is never touched.</p>"
        f'<ul class="documents">{items}</ul>'
        '<form method="post" action="/finalizar" onsubmit="return confirm(\'Finalizar sesión?\')">'
        '<button class="finalizar" type="submit">Finalizar</button></form>'
    )


def validation_error_message(exc: Exception) -> str:
    if isinstance(exc, jsonschema.ValidationError):
        return f"Schema validation failed at {list(exc.absolute_path) or '(root)'}: {exc.message}"
    return f"Could not parse this document: {exc}"


def document_page(ref: DocumentRef, content: str, error: Optional[str]) -> str:
    error_html = f'<div class="error">{escape(error)}</div>' if error else ""
    schema_note = (
        f"Validated against {escape(schema_path_for(ref.filename))} on save."
        if schema_path_for(ref.filename)
        else "No schema known for this document - saved as-is, unvalidated."
    )
    return (
        f'<p><a href="{url_for("index")}">&larr; {escape(ref.filename)}.{escape(ref.extension)}</a></p>'
        f"<h1>{escape(ref.filename)}.{escape(ref.extension)}</h1>"
        f"<p>{schema_note}</p>"
        f"{error_html}"
        '<form method="post">'
        f"<textarea name=\"content\">{escape(content)}</textarea><br><br>"
        '<button type="submit">Save</button>'
        "</form>"
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
