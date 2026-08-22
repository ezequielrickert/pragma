"""The color-picker form for `tokens.json`'s own `core.color` tokens
(ticket #154, Phase 2's first real slice - map #146's own "Not yet
specified" tracks the generic, schema-driven version this deliberately
isn't).

Reuses `interactive/customization.py::save_customized` exactly as it
is: this module's only job is turning changed `<input type="color">`
values back into the full `tokens.json` content that function already
knows how to validate and write - no new write path, no new
validation path.

Details: docs/dev/interactive/token_form.md#module
"""
from __future__ import annotations

import json
from typing import Dict

from .customization import DocumentRef, SiteOutput, effective_content, save_customized

_TOKENS_REF = DocumentRef("tokens", "json")


def color_tokens(where: SiteOutput) -> Dict[str, str]:
    """`{"core.color.<name>": "#hex", ...}` for every color token in the
    effective `tokens.json` - `core.color` is always a flat dict
    (`generators/design_tokens.py::build_tokens_document` never nests
    it), so no recursive walk is needed here the way
    `graph_export.py::token_nodes` needs for DTCG's general tree shape.
    `{}` when this site never produced a `tokens.json`.
    Details: docs/dev/interactive/token_form.md#color_tokens
    """
    content = effective_content(where, _TOKENS_REF)
    if content is None:
        return {}
    tokens_document = json.loads(content)
    return {
        f"core.color.{name}": token["$value"]
        for name, token in tokens_document.get("core", {}).get("color", {}).items()
    }


def save_color_tokens(where: SiteOutput, new_values: Dict[str, str]) -> None:
    """Patch `new_values` (`{"core.color.<name>": "#hex"}`) into the
    effective `tokens.json` and save through the exact same
    `save_customized` path every other edit uses. Submitting a token's
    own unchanged value back is a real no-op, not a special case this
    function has to detect - the resulting file's diff only ever shows
    what actually changed.
    Details: docs/dev/interactive/token_form.md#save_color_tokens
    """
    content = effective_content(where, _TOKENS_REF)
    tokens_document = json.loads(content) if content is not None else {"core": {}, "semantic": {}}
    colors = tokens_document.setdefault("core", {}).setdefault("color", {})
    for token_id, new_value in new_values.items():
        name = token_id.removeprefix("core.color.")
        if name in colors:
            colors[name]["$value"] = new_value
    content = json.dumps(tokens_document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    save_customized(where, _TOKENS_REF, content)
