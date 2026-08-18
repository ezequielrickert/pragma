"""LLM narration of a one-sentence "what is this pattern used for" purpose
per inferred component family.

Deliberately a separate module from `component_family.py`, not a function
added to it: `component_family.py`'s own module docstring commits it to
being pure/no-I/O/no-LLM (same discipline as `component_classifier.py`),
so anything that needs an `Agent` lives here instead - mirrors
`graph_prd_synthesizer.py`'s own per-item narration pattern (one
`agent.generate()` call per thing being described, graceful degradation on
a single failure rather than aborting the whole pass).

Details: docs/dev/generators/component_family_narrator.md#module
"""
from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from core.interfaces import Agent, ComponentFamily

# Details: docs/dev/generators/component_family_narrator.md#purpose_system_instruction
PURPOSE_SYSTEM_INSTRUCTION = (
    "You are labeling one reusable UI component pattern found on a web application, from the visible "
    "text of every place it's used. Write one short sentence (under 15 words) describing what this "
    "pattern is typically used for - e.g. \"confirms or submits an action\", \"cancels or dismisses a "
    "flow\", \"adjusts a numeric quantity up or down\". Describe its functional purpose only - never "
    "its visual appearance (color, size, CSS classes) and never a selector or DOM path. If the member "
    "texts don't suggest one clear common purpose, say that plainly instead of guessing."
)

# A family used site-wide (every "Buy" button on 200 product pages) has no
# other bound on how many member texts reach the prompt.
# wiki/local-and-small-model-constraints.md's own checklist named this
# exact surface. Deduplicated first (below), then capped - showing 20
# *distinct* texts is far more informative than 20 copies of "Buy", and
# dedup is also what keeps a genuinely repetitive family well under the cap
# without ever truncating it.
_MAX_TEXTS_PER_FAMILY = 20


def family_signature(family: ComponentFamily) -> Tuple:
    """A key for one family that survives re-clustering.

    Families are rebuilt from scratch every run (`record_component_families`
    DETACH DELETEs and recreates), and that is deliberate - it is what lets a
    component found on page 1 be re-clustered with page 20's evidence on a
    later pass. So a family has no stable identity to cache a narration
    against, and reusing a purpose across a membership change would leave it
    describing a group that no longer exists.

    What is stable is the family's *content*: same tag, same type, same
    shared classes, same members means the same group, whoever built it. Sort
    the members so a backend's collection order cannot change the key.
    Details: docs/dev/generators/component_family_narrator.md#family_signature
    """
    return (family.tag, family.component_type, tuple(family.common_classes), tuple(sorted(family.member_paths)))


def _deduped_and_capped(texts: List[str]) -> Tuple[List[str], int]:
    """First-seen-order dedup, then capped at `_MAX_TEXTS_PER_FAMILY`.

    Returns:
        `(shown, omitted)` - `shown` is the deduplicated, capped list;
        `omitted` is how many *distinct* texts beyond the cap were left
        out (0 if dedup alone already brought the count under the cap).
    """
    seen: Dict[str, None] = {}
    for text in texts:
        seen.setdefault(text, None)
    distinct = list(seen.keys())
    shown = distinct[:_MAX_TEXTS_PER_FAMILY]
    return shown, max(0, len(distinct) - len(shown))


def narrate_family_purposes(
    agent: Agent,
    families: List[ComponentFamily],
    member_texts: Dict[Tuple[str, str], str],
    known_purposes: Optional[Dict[Tuple, str]] = None,
) -> List[ComponentFamily]:
    """Fill in `purpose` for every family that has at least one member with
    visible text, via one `agent.generate()` call each.

    Args:
        agent: the same LLM backend `GraphPRDSynthesizer` already narrates
            pages with (`Engine` already holds one instance of this,
            shared across every narration step in a run).
        families: `component_family.build_component_families`'s output -
            each entry's own `purpose` (normally `""`, since that
            function never sets it) is what gets replaced in the
            returned list; every other field is carried over unchanged.
        member_texts: `{(page_url, path): text}` for every component
            discovered this crawl. `ComponentFamily.member_paths` only
            carries identity (which page/selector), not each member's
            own visible text - this lookup is how that text gets back in,
            without `component_family.py` itself needing to know about
            component text at all. The caller
            (`Engine._apply_component_families`) already has this,
            since it built it from the same `get_component_ledger` read
            that supplied `build_component_families`'s own input.

    Returns:
        A new list, same length and order as `families`. Each entry is
        either:
        - unchanged (via `dataclasses.replace` with no fields altered),
          if none of its members have any recorded text at all - there's
          nothing meaningful to ask the model about, so `purpose` stays
          `""` rather than spending a call on it.
        - a copy with `purpose` set to the model's one-sentence answer
          (`.strip()`ped), on a successful `agent.generate()` call.
        - a copy with `purpose` left as `""`, if `agent.generate()`
          raised for that one family - never lets one narration failure
          abort the rest of the families in `families`.

    Prints a `family i/n` line per model call. This is the slowest step
    between the end of the crawl and the first written document, and it
    was previously silent - see research/plan-progreso-en-terminal.md.
    """
    narrated: List[ComponentFamily] = []
    # Resolved once per family, up front: families with no member text are
    # skipped without a call, so the denominator has to count the calls, not
    # the families - "3/12" has to mean "3 of 12 model calls" or it stalls
    # short of its own total. Building the texts here rather than testing
    # for them twice keeps "has any text" defined in exactly one place.
    # Details: docs/dev/generators/component_family_narrator.md#narrate_family_purposes-progress
    cached = known_purposes or {}
    texts_per_family = [
        [text for text in (member_texts.get(mp, "") for mp in family.member_paths) if text]
        for family in families
    ]
    # A family whose content is unchanged since the last run keeps its
    # sentence instead of buying it again. Without this, walking a site in
    # short resumable passes re-narrates everything the earlier passes
    # already did - the cost of N passes over a growing graph, which is what
    # would make incremental crawling more expensive than one long run.
    # Details: docs/dev/generators/component_family_narrator.md#known_purposes
    reused = sum(
        1 for family, texts in zip(families, texts_per_family)
        if texts and cached.get(family_signature(family))
    )
    total_calls = sum(1 for texts in texts_per_family if texts) - reused
    if reused:
        print(f"Reusing {reused} component family purpose(s) unchanged since the last run.")
    if total_calls:
        print(f"Narrating {total_calls} component families ({total_calls} model calls)...")
    family_number = 0
    for family, texts in zip(families, texts_per_family):
        if not texts:
            narrated.append(family)
            continue
        remembered = cached.get(family_signature(family))
        if remembered:
            narrated.append(replace(family, purpose=remembered))
            continue
        family_number += 1
        # Printed before the call, not after: the whole point is showing
        # which family the run is currently blocked on.
        print(f"  family {family_number}/{total_calls}: {family.tag} ({family.component_type})")
        shown_texts, omitted = _deduped_and_capped(texts)
        prompt = (
            f"Component pattern: {family.tag} ({family.component_type})\n"
            f"Used {len(family.member_paths)} times, with these visible texts:\n"
            + "\n".join(f"- {text}" for text in shown_texts)
            + (f"\n... and {omitted} more instance(s) not shown." if omitted else "")
            + "\n\nWrite the one-sentence purpose."
        )
        try:
            purpose = agent.generate(prompt, system_instruction=PURPOSE_SYSTEM_INSTRUCTION).strip()
        except Exception:  # noqa: BLE001 - degrade this one family, not the whole pass
            purpose = ""
        narrated.append(replace(family, purpose=purpose))
    return narrated
