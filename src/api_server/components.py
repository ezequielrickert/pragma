"""`/components/*` - read-only access to the persisted component checklist.

Distinct from `/dynamic/*`: that module wraps the standing `PlaywrightScraper` session
1:1 (live, in-process browser state); this one reads `GraphStore`'s Component nodes -
durable state written by a *different* process (a `SimplePRDGenerator` CLI run), via
`graph_store: neo4j`, a shared database. `graph_store: memory` never persists across
processes, so there is nothing for a separate server process to read - these endpoints
return a clear 503 in that case rather than a bare empty result that looks like "no
components exist" instead of "this run wasn't configured to share its state."

This is what lets an external tool (or the model, via Module 3) ask "what components has
this site's crawl found, where are they, and which have actually been interacted with" -
the same checklist `_reject_premature_finish` enforces - without needing direct database
access or coupling to `SimplePRDGenerator`'s internals.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from . import graph_store_runtime

router = APIRouter(prefix="/components", tags=["components"])


def _store():
    try:
        return graph_store_runtime.get_store()
    except Exception as exc:  # noqa: BLE001 - deliberately surfaced, not logged-and-swallowed
        raise HTTPException(
            status_code=503,
            detail=(
                f"Component checklist unavailable: could not reach the Neo4j graph store ({exc}). "
                "This endpoint only works when the generator run used graph_store: neo4j (a shared "
                "database) - graph_store: memory never persists across processes, so there is "
                "nothing for this server to read."
            ),
        ) from exc


@router.get("/state")
def get_component_states(
    site: str = Query(..., description="The crawled domain, e.g. 'example.com'."),
    page_url: str = Query(..., description="The scheme-stripped page key, e.g. 'example.com/about'."),
) -> Dict[str, Dict[str, Any]]:
    """{path: {tag, text, interacted, visible, x, y, width, height}} for one page -
    the precise, position-aware checklist for everything discovered there."""
    return _store().get_component_states(site, page_url)


@router.get("/debt")
def get_pages_with_unexplored_components(
    site: str = Query(..., description="The crawled domain, e.g. 'example.com'."),
    limit: Optional[int] = Query(None),
    semantic_only: bool = Query(
        False,
        description=(
            "Exclude layer='pointer' (cursor:pointer catch-all) components. False by default here "
            "- unlike the store's own default - to match what SimplePRDGenerator's completion guard "
            "actually enforces, library-built components included."
        ),
    ),
) -> List[Dict[str, Any]]:
    """[{"url", "unexplored_count"}] - pages with real, un-interacted-with components,
    sorted descending. The revisit queue `_reject_premature_finish` reads."""
    return _store().get_pages_with_unexplored_components(site, limit=limit, semantic_only=semantic_only)
