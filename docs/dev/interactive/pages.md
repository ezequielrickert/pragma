# `interactive/pages.py`

## module

Every page `interactive/server.py`'s routes render, split out once that file crossed
`file-size-audit`'s own 300-line WATCH threshold (ticket #154) - a real, identifiable seam between
"how a page looks" and "how the server runs" (routing, threading, shutdown), the same "rendering
lives in its own file" precedent `dashboard/generic_template.py`/`dashboard/redoc_renderer.py`
already set for the static dashboard. Plain Python string building, no Jinja templates.

Every function here is pure - no disk access, no Flask app object - `url_for()` is the one Flask
dependency, and it works identically regardless of which module calls it, as long as an
app/request context is active (always true for a route handler).

## chat_panel

The chat panel on a document's own edit page (ticket #153) - every turn so far, then an input for
the next one. `chat_error` is the local model's own failure (e.g. the server is unreachable), not
a grounding gap - `grounding_for`'s own `[]` renders as a real `system_instruction` line ("no real
dependency data"), never as an error here.

## color_token_form

The `core.color.*` picker section on `tokens.json`'s own edit page (ticket #154) - `""` when this
site's `tokens.json` has no color tokens at all, so an empty section doesn't render for nothing.
Form fields are named `token:<token_id>` (`COLOR_FIELD_PREFIX`) - `server.py::save_colors` strips
that same prefix back off to know which token each submitted value belongs to.
