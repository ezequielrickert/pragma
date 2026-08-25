"""Family-aware component indexing for `pragma dynamic`.

`pragma cluster` groups repeating components (navbar links, footer
buttons, ...) into `ComponentFamily` patterns; `pragma dynamic` used to
read that grouping back to skip redundant interaction, sampling only
`max_samples` instances per family instead of clicking/filling every one.
Issue #215 dropped the skip - the same shape of bug #214 found in
`Frontier`'s content-identity dedup: a family groups components by
structural/content similarity, and that similarity can't tell "the same
repeating boilerplate control" apart from "a genuinely distinct sibling
that happens to render the same way" (mapadeprofesionales.com's repeated
professional cards each have their own "Conectar"/favorite/share button,
clustered into one `button/button` family). Every component now gets a
real interaction attempt regardless of family membership.

The family index itself (`pragma cluster`'s own `ComponentFamily`
records, and this module's membership lookup) is untouched - only the
*interaction-skipping* use of it is gone, per the same standing
direction as #214: keep building component relations/families, stop
using them to skip a per-component interaction.
Details: docs/dev/analysis/family_sampling.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.data_contracts import ComponentFamily
from spiders.content.component_matching import component_identity

# Kept for `FamilySampler.__init__`'s existing signature/callers
# (`core/dynamic_engine.py`) - no longer read by `should_interact`, which
# never skips. A future convergence signal (map #211's Not yet specified)
# may reintroduce a use for this.
# Details: docs/dev/analysis/family_sampling.md#default_max_samples_per_family
DEFAULT_MAX_SAMPLES_PER_FAMILY = 3


@dataclass
class SkippedInstance:
    """One component the sampler would have skipped under the old
    max-samples-per-family rule - kept as a type for
    `FamilySampler.skipped`'s sake, though issue #215 means nothing ever
    populates it now; `should_interact` always returns `True`.
    Details: docs/dev/analysis/family_sampling.md#skippedinstance
    """

    family_key: Tuple[str, str]
    page_key: str
    path: str
    sample_count: int


class FamilySampler:
    """Indexes each component's `pragma cluster` family membership. Built
    once per run from `pragma cluster`'s output; `should_interact` is
    called once per component the interact sweep encounters live.
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
        """Always `True` - issue #215 dropped family-membership-based
        skipping (see this module's own docstring for why). Still looks
        up and counts family membership, purely as bookkeeping a future
        convergence signal could build on; never gates the result on it.
        Details: docs/dev/analysis/family_sampling.md#should_interact
        """
        family_key = self._member_family.get((page_key, component_identity(component)))
        if family_key is not None:
            self._sample_counts[family_key] = self._sample_counts.get(family_key, 0) + 1
        return True


def _index_family_members(
    families: List[ComponentFamily], components: List[Dict[str, Any]]
) -> Dict[Tuple[str, tuple], Tuple[str, str]]:
    """`(page_key, component_identity) -> (tag, component_type)` for every
    family member - the lookup `should_interact` needs.

    A family's own `member_paths` only carries `(page_key, path)` - `path`
    is a live DOM selector that churns across separate `discover_page()`
    reloads (see
    docs/dev/spiders/orchestration/page_visitor/frontier.md#frontier's
    "History" section), so it can't be matched directly against a fresh
    interact-sweep component. `component_identity` is what survives that
    reload; this resolves each member's stored path back to the identity
    its ledger record had at clustering time, via `components` (the same
    flat ledger `pragma cluster` clustered from) - reconciled through each
    member's canonical `id` (issue #140) rather than recomputed per
    `(page_url, path)` in isolation: descriptive fields live on the
    `Component` node itself since #136, so every location a given id
    renders at reports the identical identity, and resolving through the
    id is what makes that invariant explicit instead of relying on it by
    accident.
    Details: docs/dev/analysis/family_sampling.md#_index_family_members
    """
    identity_by_id: Dict[str, tuple] = {}
    id_by_location: Dict[Tuple[str, str], str] = {}
    for c in components:
        identity_by_id.setdefault(c["id"], component_identity(c))
        id_by_location[(c["page_url"], c["path"])] = c["id"]

    index: Dict[Tuple[str, tuple], Tuple[str, str]] = {}
    for fam in families:
        family_key = (fam.tag, fam.component_type)
        for page_key, path in fam.member_paths:
            component_id = id_by_location.get((page_key, path))
            if component_id is None:
                continue
            index[(page_key, identity_by_id[component_id])] = family_key
    return index
