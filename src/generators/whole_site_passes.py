"""The two post-hoc, whole-site passes that enrich a finished crawl's graph.
Details: docs/dev/generators/whole_site_passes.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List

from ..core.interfaces import Agent, GraphStore
from .component_family import (
    build_component_families,
    label_for_tag,
    tags_with_multiple_instances,
)
from .component_family_narrator import narrate_family_purposes
from .request_family import build_inferred_requests


def _flatten_ledger(ledger: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten `get_component_ledger`'s `{page_url: {path: {...}}}` nesting
    into the flat list of dicts every whole-site pass expects, each with
    `page_url`/`path` folded in. The ledger's per-page nesting exists for
    `GraphPRDSynthesizer`'s page-by-page narration, not for passes like
    these that need to see every component at once.
    Details: docs/dev/generators/whole_site_passes.md#_flatten_ledger
    """
    return [
        {"page_url": page_url, "path": path, **record}
        for page_url, page_components in ledger.items()
        for path, record in page_components.items()
    ]


def apply_component_families(graph_store: GraphStore, site: str, agent: Agent) -> None:
    """Post-hoc, whole-site pass: infer reusable component families, give
    each a one-sentence LLM-narrated purpose, and add per-tag Neo4j
    labels - all from what the crawl just discovered, then write it back.
    Runs once, after the crawl finishes - family clustering needs to see
    every discovered component at once, not the live per-page write
    stream `MechanicalCrawler` produces during the crawl.

    Args:
        graph_store: the same `GraphStore` the just-finished crawl wrote
            to - read back from here (`get_component_ledger`), then
            written back to (`record_component_families`,
            `apply_tag_labels`).
        site: which site's just-crawled data to process.
        agent: the same LLM backend used for PRD narration - passed
            through to `narrate_family_purposes` for the one-sentence
            "what is this pattern used for" description each family gets.

    Returns:
        None. Four steps, always in this order:
        1. Read every discovered component for `site` via
           `get_component_ledger` and flatten it (`_flatten_ledger`) into
           the shape `component_family.build_component_families`/
           `tags_with_multiple_instances` both expect.
        2. `build_component_families` clusters that flat list into
           `ComponentFamily` objects (see that function's own docstring
           for the full algorithm) - `purpose` is still `""` on every one
           at this point, since clustering itself never calls the model.
        3. `narrate_family_purposes` fills in `purpose`, one
           `agent.generate()` call per family that has any member text at
           all - see that function's own docstring for its graceful-
           degradation behavior on a single family's failure.
        4. The narrated families are written via `record_component_
           families` (a full rebuild of `site`'s family structure every
           call, per that method's own contract), and
           `tags_with_multiple_instances` picks which raw HTML tags
           appear often enough to deserve their own Neo4j label, each
           mapped through `label_for_tag` to its actual label string
           (e.g. `"button"` -> `"Button"`), written via
           `apply_tag_labels`.
    Details: docs/dev/generators/whole_site_passes.md#apply_component_families
    """
    components = _flatten_ledger(graph_store.get_component_ledger(site))
    families = build_component_families(components)
    member_texts = {(c["page_url"], c["path"]): c.get("text", "") for c in components}
    families = narrate_family_purposes(agent, families, member_texts)
    graph_store.record_component_families(site, families)

    tags = tags_with_multiple_instances(components)
    graph_store.apply_tag_labels(site, {tag: label_for_tag(tag) for tag in tags})


def apply_request_graph(graph_store: GraphStore, site: str) -> None:
    """Post-hoc, whole-site pass: infer distinct API endpoints (and which
    Components trigger each one) from network requests already captured
    on Component nodes, then write them back. Independent of - and reads
    the graph a second time from - `apply_component_families`, rather
    than sharing its already-flattened `components` list: this keeps the
    two passes fully separable (one about component *look-alikes*, this
    one about *endpoint* identity), at the cost of one extra
    `get_component_ledger` read per crawl - a single local read, not a
    hot path, run once per whole crawl.

    Args:
        graph_store: same `GraphStore` the crawl wrote to.
        site: which site's just-crawled data to process.

    Returns:
        None. Reads every discovered component's `network_requests` via
        `get_component_ledger`, flattens it with `_flatten_ledger`,
        clusters them via
        `request_family.build_inferred_requests` (see that function's own
        docstring), and writes the result via `record_inferred_requests`
        - a full rebuild of `site`'s inferred-request structure every
        call, same contract as `record_component_families`.
    Details: docs/dev/generators/whole_site_passes.md#apply_request_graph
    """
    components = _flatten_ledger(graph_store.get_component_ledger(site))
    graph_store.record_inferred_requests(site, build_inferred_requests(components))


