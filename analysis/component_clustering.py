"""Whole-site component-family clustering: read every discovered component
back from the graph store, group them into reusable `ComponentFamily`
patterns, narrate each with the LLM, write the result back.

Extracted from `core/engine.py::_apply_component_families` so `pragma
cluster` (a standalone command, not a phase of the fused crawl+analyze
run) and `Engine._run_async` share one implementation instead of two
copies drifting apart. Its own module, not folded into
`generators/component_family.py`, for the same reason
`component_family_narrator.py` is separate from that file: clustering
itself is pure/no-I/O, this function is the one that reads and writes.
Details: docs/dev/analysis/component_clustering.md#module
"""
from __future__ import annotations

from typing import Any

from core.interfaces import Agent
from generators.component_family import build_component_families
from generators.component_family_narrator import family_signature, narrate_family_purposes
from generators.ledger import flat_component_ledger


def apply_component_families(graph_store: Any, agent: Agent) -> None:
    """Post-hoc, whole-site pass: infer reusable component families, give
    each a one-sentence LLM-narrated purpose, then write it back. Runs
    once, over every component the graph store currently holds - family
    clustering needs to see them all at once, not a live per-page write
    stream.

    Args:
        graph_store: the store to read from (`get_component_ledger`) and
            write back to (`record_component_families`) - site-scoped by
            construction (one store per site), so no `site` argument here
            or on any of the calls below. Whatever wrote it (`pragma
            static`, or `Engine`'s own fused crawl) doesn't matter to
            this function; it only reads what's already there.
        agent: the LLM backend used for the one-sentence "what is this
            pattern used for" description each family gets.

    Returns:
        None. Three steps, always in this order:
        1. Read every discovered component via
           `ledger.flat_component_ledger` - see that function's own
           docstring for why the ledger's per-page nesting has to be
           flattened for a whole-site pass like this one.
        2. `build_component_families` clusters that flat list into
           `ComponentFamily` objects (see that function's own docstring
           for the full algorithm) - `purpose` is still `""` on every one
           at this point, since clustering itself never calls the model.
        3. `narrate_family_purposes` fills in `purpose`, one
           `agent.generate()` call per family that has any member text at
           all - see that function's own docstring for its graceful-
           degradation behavior on a single family's failure - and the
           narrated families are written via `record_component_families`
           (a full rebuild of the site's family structure every call, per
           that method's own contract).
    Details: docs/dev/analysis/component_clustering.md#apply_component_families
    """
    components = flat_component_ledger(graph_store)
    families = build_component_families(components)
    print(f"Grouped {len(components)} components into {len(families)} families.")
    member_texts = {(c["page_url"], c["path"]): c.get("text", "") for c in components}
    # Read before record_component_families wipes them: a family whose members
    # did not change keeps its sentence rather than buying it again, which is
    # what keeps a site crawled in short resumable passes from re-narrating
    # everything every pass. Details: docs/dev/analysis/component_clustering.md#known-purposes
    known_purposes = {
        family_signature(existing): existing.purpose
        for existing in graph_store.get_component_families()
        if existing.purpose
    }
    families = narrate_family_purposes(agent, families, member_texts, known_purposes)
    graph_store.record_component_families(families)
