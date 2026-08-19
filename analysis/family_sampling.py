"""Family-aware interaction sampling for `pragma dynamic`.

`pragma cluster` groups repeating components (navbar links, footer
buttons, ...) into `ComponentFamily` patterns; `pragma dynamic` reads
that grouping back to skip redundant interaction on components already
known to belong to a repeating family, sampling only `max_samples`
instances per family instead of clicking/filling every one - the whole
point of resuming from `static` + `cluster` output instead of
re-discovering the site from scratch.
Details: docs/dev/analysis/family_sampling.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.data_contracts import ComponentFamily
from spiders.content.component_matching import component_identity

# How many members of a family `pragma dynamic` actually interacts with
# before it starts skipping the rest - the ticket's own "2-3 instances"
# call; 3 rather than 2, since a family whose second sample happened to
# be atypical (a disabled state, an empty search box) would otherwise
# have nothing else to compare it against.
# Details: docs/dev/analysis/family_sampling.md#default_max_samples_per_family
DEFAULT_MAX_SAMPLES_PER_FAMILY = 3


@dataclass
class SkippedInstance:
    """One component the sampler decided not to interact with - kept as
    data, not just a print line, so a caller (a run summary, a test) can
    inspect what got skipped without scraping stdout.
    Details: docs/dev/analysis/family_sampling.md#skippedinstance
    """

    family_key: Tuple[str, str]
    page_key: str
    path: str
    sample_count: int


class FamilySampler:
    """Caps how many members of each `ComponentFamily` a dynamic run
    actually interacts with. Built once per run from `pragma cluster`'s
    output; `should_interact` is called once per component the interact
    sweep encounters live.
    Details: docs/dev/analysis/family_sampling.md#familysampler
    """

    def __init__(
        self,
        families: List[ComponentFamily],
        components: List[Dict[str, Any]],
        max_samples: int = DEFAULT_MAX_SAMPLES_PER_FAMILY,
    ) -> None:
        self.max_samples = max_samples
        self.skipped: List[SkippedInstance] = []
        self._sample_counts: Dict[Tuple[str, str], int] = {}
        self._member_family = _index_family_members(families, components)

    def should_interact(self, page_key: str, component: Dict[str, Any]) -> bool:
        """Whether the live interact sweep should click/fill `component`,
        or skip it as an already-sampled family member.

        A component with no known family (never clustered, or clustering
        never ran) always returns `True` - sampling only ever narrows a
        crawl that already has a family to sample from, never blocks one
        that doesn't.
        Details: docs/dev/analysis/family_sampling.md#should_interact
        """
        family_key = self._member_family.get((page_key, component_identity(component)))
        if family_key is None:
            return True
        count = self._sample_counts.get(family_key, 0) + 1
        self._sample_counts[family_key] = count
        if count <= self.max_samples:
            return True
        path = component.get("path", "")
        self.skipped.append(SkippedInstance(family_key, page_key, path, count))
        tag, component_type = family_key
        print(
            f"  family-sampled: skipping {component_type!r} on {page_key} "
            f"(instance #{count} of {tag}/{component_type}, already sampled {self.max_samples})"
        )
        return False


def _index_family_members(
    families: List[ComponentFamily], components: List[Dict[str, Any]]
) -> Dict[Tuple[str, tuple], Tuple[str, str]]:
    """`(page_key, component_identity) -> (tag, component_type)` for every
    family member - the lookup `should_interact` needs.

    A family's own `member_paths` only carries `(page_key, path)` - `path`
    is a live DOM selector that churns across separate `discover_page()`
    reloads (see
    docs/dev/spiders/orchestration/page_visitor/frontier.md#_navigation_trigger_identities),
    so it can't be matched directly against a fresh interact-sweep
    component. `component_identity` is what survives that reload; this
    resolves each member's stored path back to the identity its ledger
    record had at clustering time, via `components` (the same flat
    ledger `pragma cluster` clustered from).
    Details: docs/dev/analysis/family_sampling.md#_index_family_members
    """
    identity_by_location = {
        (c["page_url"], c["path"]): component_identity(c) for c in components
    }
    index: Dict[Tuple[str, tuple], Tuple[str, str]] = {}
    for fam in families:
        family_key = (fam.tag, fam.component_type)
        for page_key, path in fam.member_paths:
            identity = identity_by_location.get((page_key, path))
            if identity is None:
                continue
            index[(page_key, identity)] = family_key
    return index
