"""Interact-once tracking for `pragma dynamic`'s live interact sweep -
issue #135's design, wired for real (issue #140).

A `Component` row reused across 2+ pages - the exact tier's own
definition, the same criterion `analysis/component_matching_pipeline.py::
_leaf_merge_groups` merges rows on, made visible again at read time -
gets interacted with at most once, ever, per run: the first successful
interaction with it marks it interacted in memory (mirroring
`record_component_interaction`'s own `c.interacted = true` write, kept
here too so a concurrent page worker sees the flip immediately rather
than waiting on a fresh DB read), and every other page rendering the
same canonical row gets its outcome inferred instead of independently
re-clicked.

Deliberately not routed through `analysis/family_sampling.py::
FamilySampler` - a family is several *distinct* components judged merely
similar; exact reuse is the *same* canonical `Component` row rendered on
several pages, a stronger claim that earns a stronger inference (skip
forever after one real interaction, not after N samples).
Details: docs/dev/analysis/exact_reuse_index.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from spiders.content.component_matching import component_identity

# A page-scoped location a canonical component renders at - `page_url` is
# actually the route-shape `page_key` every Page node is keyed by, not a
# literal URL (see `_record_discovery`'s `record_page_arrival(page_key, ...)`).
Location = Tuple[str, str]


@dataclass
class ReuseEntry:
    """One canonical `Component` reused across `locations`. `interacted`
    starts at whatever the ledger already knew (a prior run's real
    interaction), then flips the instant this run interacts with it
    anywhere - checked and set synchronously, with no `await` in
    between, so two concurrent page workers racing the same canonical
    component can't both decide to interact.
    Details: docs/dev/analysis/exact_reuse_index.md#reuseentry
    """

    component_id: str
    locations: Tuple[Location, ...]
    interacted: bool

    def siblings_of(self, location: Location) -> List[Location]:
        """Every other page this same canonical component also renders
        on - what an inferred `NAVIGATES_TO` gets written for once this
        run's one real interaction resolves.
        Details: docs/dev/analysis/exact_reuse_index.md#siblings_of
        """
        return [loc for loc in self.locations if loc != location]


class ExactReuseIndex:
    """`(page_key, live component) -> ReuseEntry` for every canonical
    `Component` rendered on 2+ pages - built once per `pragma dynamic`
    run from `generators/ledger.py::flat_component_ledger`'s output, the
    same snapshot `analysis/family_sampling.py::FamilySampler` is built
    from.

    A component rendered on exactly one page is never exact-tier reuse -
    nothing to infer, so it's absent from this index entirely and
    `lookup` returns `None` for it, same as when clustering never ran.
    Details: docs/dev/analysis/exact_reuse_index.md#exactreuseindex
    """

    def __init__(self, components: List[Dict[str, Any]]) -> None:
        # Every location the interact sweep skipped as an already-
        # interacted exact-tier reuse - kept as data, not just a print
        # line, the same reasoning `FamilySampler.skipped` follows, so a
        # run summary can report it.
        # Details: docs/dev/analysis/exact_reuse_index.md#skipped
        self.skipped: List[Location] = []
        by_id: Dict[str, List[Dict[str, Any]]] = {}
        for component in components:
            by_id.setdefault(component["id"], []).append(component)

        self._by_identity: Dict[Tuple[str, tuple], ReuseEntry] = {}
        for component_id, members in by_id.items():
            locations = tuple(sorted({(m["page_url"], m["path"]) for m in members}))
            if len(locations) < 2:
                continue
            entry = ReuseEntry(
                component_id=component_id,
                locations=locations,
                interacted=any(m.get("interacted") for m in members),
            )
            # Descriptive fields (`tag`/`text`/`role`/...) live on the
            # Component node itself post-#136, not on the per-page edge -
            # every member here reports the identical value for them, so
            # one member's identity speaks for every location this id
            # renders at, no per-location recomputation needed.
            identity = component_identity(members[0])
            for page_key, _path in locations:
                self._by_identity[(page_key, identity)] = entry

    def lookup(self, page_key: str, component: Dict[str, Any]) -> Optional[ReuseEntry]:
        """The reuse entry a live-discovered `component` belongs to, or
        `None` when it isn't part of any exact-tier reuse.
        Details: docs/dev/analysis/exact_reuse_index.md#lookup
        """
        return self._by_identity.get((page_key, component_identity(component)))
