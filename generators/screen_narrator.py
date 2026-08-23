"""LLM narration of `Screen.name`/`Screen.purpose` - one `agent.generate()`
call per Screen, returning both fields from a single prompt/response
(per 'Define Screen semantics and derivation algorithm', issue #188).

Deliberately a separate module from `screens.py`, not a function added to
it: `screens.py`'s own module docstring commits it to being pure/no-I/O/
no-LLM, so anything that needs an `Agent` lives here instead - the same
split `component_family_narrator.py` keeps from `component_family.py`,
and this module mirrors its narration pattern directly (one call per
item, graceful degradation on a single failure, signature-based reuse so
a rebuild doesn't re-narrate an unchanged Screen).

Details: docs/dev/generators/screen_narrator.md#module
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from core.interfaces import Agent, SemanticScreen

# Details: docs/dev/generators/screen_narrator.md#screen_system_instruction
SCREEN_SYSTEM_INSTRUCTION = (
    "You are labeling one screen of a web application, from its page title, meta description and "
    "route. Answer in exactly two lines, nothing else:\n"
    "NAME: a short (2-5 word) human-readable screen name, e.g. \"Product listing\", \"Checkout\"\n"
    "PURPOSE: one short sentence (under 15 words) describing what a person does on this screen\n"
    "Describe function only - never visual appearance, color or layout. If the title/description "
    "don't suggest a clear name or purpose, say that plainly on that line instead of guessing."
)

_NAME_LINE_RE = re.compile(r"^\s*NAME:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
_PURPOSE_LINE_RE = re.compile(r"^\s*PURPOSE:\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def build_page_context(page_titles: Dict[str, str], page_descriptions: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
    """`{page_url: (title, description)}` for every page with either -
    `narrate_screens`'s `page_context` argument, assembled from
    `graph_store.get_page_titles()`/`get_page_descriptions()`.
    Details: docs/dev/generators/screen_narrator.md#build_page_context
    """
    return {
        url: (page_titles.get(url, ""), page_descriptions.get(url, ""))
        for url in page_titles.keys() | page_descriptions.keys()
    }


def screen_signature(screen: SemanticScreen) -> Tuple[str, str]:
    """A key for one screen that survives a full rebuild.

    Screens are rewritten from scratch every run (`record_screens`
    `DETACH DELETE`s and recreates, same as `record_component_families`),
    so a screen has no stable node id to cache a narration against across
    runs. What is stable is `page_url` - a Screen's whole identity, since
    the tier is 1:1 with `Page` - paired with `route_pattern` so a screen
    whose route classification changed (a crawl config edit, say) is
    re-narrated rather than silently keeping a stale name.
    Details: docs/dev/generators/screen_narrator.md#screen_signature
    """
    return (screen.page_url, screen.route_pattern)


def _parse_response(text: str) -> Tuple[str, str]:
    """`(name, purpose)` from the model's two labeled lines, or `("", "")`
    if the response doesn't carry the expected shape - the same graceful-
    degradation contract `narrate_family_purposes` gives a failed call,
    extended to a malformed one, since a two-field response has a way to
    come back structurally broken that a one-sentence one does not.
    Details: docs/dev/generators/screen_narrator.md#_parse_response
    """
    name_match = _NAME_LINE_RE.search(text)
    purpose_match = _PURPOSE_LINE_RE.search(text)
    name = name_match.group(1).strip() if name_match else ""
    purpose = purpose_match.group(1).strip() if purpose_match else ""
    return name, purpose


def narrate_screens(
    agent: Agent,
    screens: List[SemanticScreen],
    page_context: Dict[str, Tuple[str, str]],
    known_purposes: Optional[Dict[Tuple[str, str], Tuple[str, str]]] = None,
) -> List[SemanticScreen]:
    """Fill in `name`/`purpose` for every screen that has a title or a
    description to narrate from, via one `agent.generate()` call each.

    Args:
        agent: the same LLM backend `Engine` shares across every
            narration step in a run.
        screens: `build_screens`'s output - each entry's own `name`/
            `purpose` (always `""`, since `build_screens` never sets
            them) is what gets replaced in the returned list.
        page_context: `{page_url: (title, description)}`, mirroring
            `narrate_family_purposes`'s own `member_texts` - one dict
            carrying both signals a screen is narrated from, built from
            `graph_store.get_page_titles()`/`get_page_descriptions()`
            (`build_page_context`, this module).
        known_purposes: `{screen_signature(screen): (name, purpose)}`
            from the previous run's screens, read before
            `record_screens` wipes them - a screen unchanged since then
            keeps its sentence instead of buying it again, same reasoning
            `narrate_family_purposes`'s own `known_purposes` follows.

    Returns:
        A new list, same length and order as `screens`. Each entry is
        either unchanged (no title and no description to ask about),
        a copy carrying the previous run's `(name, purpose)` (unchanged
        signature), or a copy carrying a fresh `agent.generate()` answer
        - `("", "")` if that call raised or came back malformed, never
        letting one screen's failure abort the rest.

    Prints a `screen i/n` line per model call, the same progress
    reporting `narrate_family_purposes` gives the slowest step in a run.
    Details: docs/dev/generators/screen_narrator.md#narrate_screens
    """
    cached = known_purposes or {}
    contexts = [page_context.get(screen.page_url, ("", "")) for screen in screens]
    reused = sum(
        1 for screen, (title, description) in zip(screens, contexts)
        if (title or description) and screen_signature(screen) in cached
    )
    total_calls = sum(1 for title, description in contexts if title or description) - reused
    if reused:
        print(f"Reusing {reused} screen name/purpose pair(s) unchanged since the last run.")
    if total_calls:
        print(f"Narrating {total_calls} screens ({total_calls} model calls)...")

    narrated: List[SemanticScreen] = []
    screen_number = 0
    for screen, (title, description) in zip(screens, contexts):
        if not (title or description):
            narrated.append(screen)
            continue
        remembered = cached.get(screen_signature(screen))
        if remembered:
            name, purpose = remembered
            narrated.append(replace(screen, name=name, purpose=purpose))
            continue
        screen_number += 1
        print(f"  screen {screen_number}/{total_calls}: {screen.route_pattern}")
        prompt = (
            f"Route: {screen.route_pattern}\n"
            f"Page title: {title or '(none)'}\n"
            f"Meta description: {description or '(none)'}"
        )
        try:
            response = agent.generate(prompt, system_instruction=SCREEN_SYSTEM_INSTRUCTION)
            name, purpose = _parse_response(response)
        except Exception:  # noqa: BLE001 - degrade this one screen, not the whole pass
            name, purpose = "", ""
        narrated.append(replace(screen, name=name, purpose=purpose))
    return narrated
