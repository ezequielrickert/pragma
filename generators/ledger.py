"""The one place that turns `get_component_ledger`'s nested
`{page_url: {path: record}}` shape into the flat `[{page_url, path, ...}]`
list every whole-site pass wants.

Why this exists: the nesting is right for `GraphPRDSynthesizer`, which
narrates one page at a time. It is wrong for every pass that reasons
across the whole site at once - component families, inferred requests,
and every document generator this project is about to grow. Those all
need the same flattening, and before this module `Engine` carried two
byte-identical copies of it with more on the way.

Details: docs/dev/generators/ledger.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List


def flat_component_ledger(graph_store: Any) -> List[Dict[str, Any]]:
    """Every component the site's crawl discovered, as one flat list.

    Args:
        graph_store: the store the crawl wrote to. Read-only here,
            already scoped to exactly one site by construction.

    Returns:
        One dict per discovered component, each carrying its own
        `page_url` and `path` folded in alongside everything
        `get_component_ledger` already recorded for it (`text`, `tag`,
        `component_type`, `interactions`, `network_requests`, ...).
        `[]` when the site has no components recorded.

        Order follows the ledger's own iteration order, which neither
        shipped backend guarantees to be meaningful - callers that need
        a stable order sort it themselves, the same way
        `build_component_families` and `build_inferred_requests`
        already do.
    """
    ledger = graph_store.get_component_ledger()
    return [
        {"page_url": page_url, "path": path, **record}
        for page_url, page_components in ledger.items()
        for path, record in page_components.items()
    ]
