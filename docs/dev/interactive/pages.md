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

**First real client-side JS in this app** (ticket #155, `_DIFF_GUTTER_JS`): the raw-text editor's
diff/error gutter repaints on every keystroke, which only a client-side line-diff can do without
round-tripping to the server per keystroke. Distinct from ADR-0034's separate zero-JS decision for
the *generic form*'s row add/remove UX - that's a different feature with a different constraint
(a discrete action, not a per-keystroke one), not a reversal of this one.

## ValidationFailure

A failed save's message plus the real jsonschema data path (`exc.absolute_path`) - `document_page`
turns that path into an approximate gutter line marker (ticket #155), not just a plain-text
banner. `path` is never a source line number; jsonschema only ever carries a data path.

## DocumentEditState

`content` (what the textarea shows/submits) and `original` (the crawl's own output, read-only,
for the diff pane) bundled per `python-clean-code`'s F1 (max 3 args), matching
`SiteOutput`/`DocumentRef`'s own precedent - `document_page` would otherwise need 4+ positional
args once the diff view (ticket #155) needed both documents at once.

## _approximate_line_for_path

The best guess at which line of `content` a jsonschema error's data path corresponds to - the last
path segment that looks like a real key, searched as a quoted JSON string. `None` when nothing
matches, or the match is ambiguous (found on more than one line) - deliberately: a wrong guess
would point a reviewer at the wrong line, which is worse than admitting the line can't be found.

## document_page

The raw-text editor: two side-by-side panes (`state.original`, read-only; `state.content`, the
live `<textarea>` a save submits) each with a synced-scroll gutter marking changed lines - ticket
#155's own diff view, replacing the plain single-textarea/plain-error version #151 first shipped.
The gutter is repainted client-side on every keystroke (`paintGutters`, `_DIFF_GUTTER_JS`'s own
line-level LCS diff) rather than server-side, since the "current" side changes with every
keystroke and round-tripping that to the server for every keystroke would make the editor feel
laggy for no real benefit. A `state.failure` additionally marks its `_approximate_line_for_path`
result in the current pane's own gutter, on top of the plain-text `error_html` banner
(`ValidationFailure.message`) - the banner explains what's wrong, the gutter marker points at
roughly where.

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
