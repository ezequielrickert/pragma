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
from typing import Dict, List, Tuple

from ..core.interfaces import Agent, ComponentFamily

# Details: docs/dev/generators/component_family_narrator.md#purpose_system_instruction
PURPOSE_SYSTEM_INSTRUCTION = (
    "You are labeling one reusable UI component pattern found on a web application, from the visible "
    "text of every place it's used. Write one short sentence (under 15 words) describing what this "
    "pattern is typically used for - e.g. \"confirms or submits an action\", \"cancels or dismisses a "
    "flow\", \"adjusts a numeric quantity up or down\". Describe its functional purpose only - never "
    "its visual appearance (color, size, CSS classes) and never a selector or DOM path. If the member "
    "texts don't suggest one clear common purpose, say that plainly instead of guessing."
)


def narrate_family_purposes(
    agent: Agent,
    families: List[ComponentFamily],
    member_texts: Dict[Tuple[str, str], str],
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
    """
    narrated: List[ComponentFamily] = []
    for family in families:
        texts = [text for text in (member_texts.get(mp, "") for mp in family.member_paths) if text]
        if not texts:
            narrated.append(family)
            continue
        prompt = (
            f"Component pattern: {family.tag} ({family.component_type})\n"
            f"Used {len(family.member_paths)} times, with these visible texts:\n"
            + "\n".join(f"- {text}" for text in texts)
            + "\n\nWrite the one-sentence purpose."
        )
        try:
            purpose = agent.generate(prompt, system_instruction=PURPOSE_SYSTEM_INSTRUCTION).strip()
        except Exception:  # noqa: BLE001 - degrade this one family, not the whole pass
            purpose = ""
        narrated.append(replace(family, purpose=purpose))
    return narrated
