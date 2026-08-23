"""Screen derivation: one `SemanticScreen` per `Page`, deduced from the
navigation graph alone, per `docs/dev/database/ladybug/screen.md` (the
Screen writer, mirroring `data_model.py` + `semantic.py::record_entities`).

**One `Screen` per `Page`, 1:1 - not clustered.** The screen-clustering
research this ticket followed (issue #185) found that `Page.route_shape`
plus `ComponentFamily` membership overlap already give cheap route-template
and DOM-structural signals, but naming a cluster as one human-meaningful
screen type - and telling apart two same-route-shape Pages that are
semantically different templates - still needs heuristic/LLM judgment this
tier's deterministic half can't supply. 1:1 sidesteps that judgment call
entirely rather than guessing at it: `route_pattern` is still the grouping
signal a reader can use to spot same-template Pages themselves, just not
collapsed into a single node that would hide which Pages fed it.

Pure and deterministic, no model call - `name`/`purpose` narration is a
separate, impure step in `screen_narrator.py`, the same split
`component_family_narrator.py` keeps from `component_family.py`.

Details: docs/dev/generators/screens.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence

from core.interfaces import SemanticScreen
from utils.urls import route_shape


def build_screens(pages: Sequence[Dict[str, Any]]) -> List[SemanticScreen]:
    """One `SemanticScreen` per finished `Page`, sorted by url.

    Args:
        pages: `graph_store.get_progress_table_rows()`'s own shape
            (`{"url", "status", "components"}` per page).

    Returns:
        A `SemanticScreen` for every page with `status == "Finished"`,
        `route_pattern` computed via `route_shape` - which already strips
        any `#state:...` fragment a synthetic in-page-state Page's `url`
        carries, the same way it strips any other URL fragment. A
        `"Pending"`/`"Scouted"` page has no rendered content yet, so it
        gets no Screen: there is nothing to say a screen *renders*.
    Details: docs/dev/generators/screens.md#build_screens
    """
    return sorted(
        (
            SemanticScreen(page_url=page["url"], route_pattern=route_shape(page["url"]))
            for page in pages
            if page.get("status") == "Finished"
        ),
        key=lambda screen: screen.page_url,
    )
