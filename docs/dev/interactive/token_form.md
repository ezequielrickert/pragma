# `interactive/token_form.py`

## module

The color-picker form for `tokens.json`'s own `core.color` tokens (ticket #154, Phase 2's first
real slice - map #146's own "Not yet specified" tracks the generic, schema-driven version this
deliberately isn't).

Reuses `interactive/customization.py::save_customized` exactly as it is: this module's only job is
turning changed `<input type="color">` values back into the full `tokens.json` content that
function already knows how to validate and write - no new write path, no new validation path.

## color_tokens

`{"core.color.<name>": "#hex", ...}` for every color token in the effective `tokens.json` -
`core.color` is always a flat dict (`generators/design_tokens.py::build_tokens_document` never
nests it), so no recursive walk is needed here the way `graph_export.py::token_nodes` needs for
DTCG's general tree shape. `{}` when this site never produced a `tokens.json`.

## save_color_tokens

Patches the given token ids into the effective `tokens.json` and saves through the exact same
`save_customized` path every other edit uses. Submitting a token's own unchanged value back is a
real no-op, not a special case this function has to detect - the resulting file's diff only ever
shows what actually changed, satisfying ticket #154's own "feels like editing one token" requirement
without any explicit change-detection logic. An id the document no longer has (a stale form
submission) is silently skipped, not an error - the document may have changed between page load and
save.
