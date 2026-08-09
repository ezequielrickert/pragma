"""Deterministic component classification and grouping - the "what is this, what does
it offer, what state is it in" facts an LLM narration pass (see
`SimplePRDGenerator._write_component_catalog`) turns into readable documentation.

Every function here is pure and DOM-attribute-driven, no model call involved - matches
this project's established preference (see wiki/local-and-small-model-constraints.md)
for deterministic, code-side signals over model judgment wherever the underlying facts
are already mechanically knowable. A small/weak local model narrates these facts into
prose; it never has to *notice* them itself.
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List, Optional

# role values that mark a member of an enumerable list (a dropdown/combobox/menu's
# individual choices) - see `find_revealed_options`.
_OPTION_ROLES = {"option", "menuitem", "menuitemcheckbox", "menuitemradio", "tab"}

# Increment/decrement label vocabulary, English + Spanish (this project already
# crawls Spanish-labelled sites - see SimplePRDGenerator._generate_field_value's
# equivalent accent-stripped matching for text field values) - matched against a
# component's own text/aria-label after accent-stripping and lowercasing.
_INCREMENT_WORDS = {"agregar", "sumar", "mas", "add", "increase", "increment", "plus", "+"}
_DECREMENT_WORDS = {"restar", "quitar", "menos", "remove", "decrease", "decrement", "minus", "-"}


def _normalize(text: str) -> str:
    """Lowercase, accent-stripped comparison key - mirrors
    SimplePRDGenerator._generate_field_value's normalization so both stay
    consistent for the same vocabulary-matching purpose."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return text.strip().lower()


def classify_component_type(comp: Dict[str, Any]) -> str:
    """A short, human-readable type label from tag/role/input_type alone -
    no LLM call, no page context needed. This is the label the component
    catalog's narration prompt is built around; the model is told what kind
    of thing it's describing rather than asked to guess from raw HTML.
    """
    tag = (comp.get("tag") or "").lower()
    role = (comp.get("role") or "").lower()
    input_type = (comp.get("input_type") or "").lower()

    if role in ("option", "menuitem", "menuitemcheckbox", "menuitemradio"):
        return "list/menu option"
    if role == "combobox":
        return "combobox (searchable dropdown)"
    if role == "checkbox" or input_type == "checkbox":
        return "checkbox"
    if role == "radio" or input_type == "radio":
        return "radio button"
    if role == "switch":
        return "toggle switch"
    if role == "tab":
        return "tab"
    if tag == "select":
        return "native dropdown (select)"
    if tag in ("input", "textarea"):
        return f"text field ({input_type or 'text'})"
    if tag == "button" and input_type == "submit":
        return "submit button"
    if tag == "button":
        return "button"
    if tag == "a":
        return "link"
    if comp.get("discovery_layer") == "pointer":
        return "custom control (component-library element, no native tag/role)"
    return "element"


def find_revealed_options(before: List[dict], after: List[dict]) -> List[Dict[str, Any]]:
    """Components with an "option"-family role that a trigger's click/fill
    just made available - either genuinely new to the DOM (matched by CSS
    path not present in `before` at all - a React/Radix-portal widget that
    mounts its popover content on open), OR already present in `before` but
    CSS-hidden (`visible: False`) and now `visible: True` in `after` - the
    other common pattern (a plain `hidden`/`display:none` toggle, the same
    "present in the DOM the whole time, just hidden until a trigger" shape
    `PlaywrightScraper._discover_components`'s own mega-menu handling already
    assumes elsewhere). Both are "the user can now see and act on this that
    they couldn't a moment ago" - the property this function actually exists
    to detect - so both count as revealed.

    A component with no `visible` key at all in either snapshot (a caller
    that doesn't track it) is never treated as newly-revealed via the
    became-visible path - only the by-path-absence check applies for it -
    preserving this function's original behavior for such callers.

    Called from `MechanicalCrawler._visit_page` comparing a page's component
    list immediately before vs. after a same-page interaction - this is the
    concrete "clicking 'Tercera Docena' revealed a 9-item bakery picker" case:
    the trigger itself doesn't carry its own options in a single DOM
    snapshot, they only exist once it's been opened, so this has to be a
    before/after diff, not a single-snapshot classification like the other
    functions here.
    """
    before_by_path = {c.get("path"): c for c in before}
    revealed = []
    for c in after:
        if (c.get("role") or "").lower() not in _OPTION_ROLES:
            continue
        prior = before_by_path.get(c.get("path"))
        if prior is None:
            is_new = True
        else:
            is_new = prior.get("visible") is False and c.get("visible") is True
        if is_new:
            revealed.append({"text": (c.get("text") or "").strip(), "selected": bool(c.get("selected"))})
    return revealed


def _parent_path(path: str) -> str:
    """The CSS path of `path`'s immediate parent (see `gp()` in
    PlaywrightScraper._discover_components - paths are ' > '-joined segments),
    used as a same-container grouping key for sibling elements."""
    segments = (path or "").split(" > ")
    return " > ".join(segments[:-1])


def _looks_numeric(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(stripped) and any(ch.isdigit() for ch in stripped) and all(
        ch.isdigit() or ch in ".,+- " for ch in stripped
    )


def group_steppers(components: List[dict]) -> List[Dict[str, Any]]:
    """Detect increment/decrement button pairs sharing a common parent container
    (a quantity stepper: "-" / count / "+") and, if present, the numeric-looking
    sibling between them.

    Grouping key is the shared *parent* CSS path, not any single component's own
    identity - a stepper's "+"/"-" buttons are siblings under one container, and
    grouping by that container is what ties them together as one logical control
    rather than three unrelated buttons/text. Returns one entry per detected
    stepper; a page with no such pattern returns an empty list, cheaply.
    """
    groups: Dict[str, List[dict]] = {}
    for comp in components:
        path = comp.get("path") or ""
        if not path:
            continue
        groups.setdefault(_parent_path(path), []).append(comp)

    steppers = []
    for container, members in groups.items():
        if len(members) < 2 or not container:
            continue
        increment = next(
            (m for m in members if _normalize(m.get("text") or m.get("attributes", {}).get("aria-label", "")) in _INCREMENT_WORDS),
            None,
        )
        decrement = next(
            (m for m in members if _normalize(m.get("text") or m.get("attributes", {}).get("aria-label", "")) in _DECREMENT_WORDS),
            None,
        )
        if not increment or not decrement:
            continue
        value_member = next(
            (m for m in members if m is not increment and m is not decrement and _looks_numeric(m.get("text") or m.get("value") or "")),
            None,
        )
        steppers.append(
            {
                "container": container,
                "increment_path": increment.get("path"),
                "decrement_path": decrement.get("path"),
                "value_path": value_member.get("path") if value_member else None,
                "current_value": (value_member.get("text") or value_member.get("value")) if value_member else None,
            }
        )
    return steppers


def group_choice_sets(components: List[dict]) -> Dict[str, List[dict]]:
    """Radio/checkbox components sharing the same `name` attribute - the standard
    HTML pattern for "these inputs are one logical choice, not independent
    fields" (a single radio input alone isn't meaningfully describable without
    its siblings; a whole named group is what a human would call "one control").

    Groups of size 1 are dropped - nothing to group without at least one
    sibling sharing the same `name`.
    """
    groups: Dict[str, List[dict]] = {}
    for comp in components:
        role = (comp.get("role") or "").lower()
        input_type = (comp.get("input_type") or "").lower()
        name = comp.get("name") or ""
        if not name or (role not in ("radio", "checkbox") and input_type not in ("radio", "checkbox")):
            continue
        groups.setdefault(name, []).append(comp)
    return {name: members for name, members in groups.items() if len(members) >= 2}


def describe_options(options_json: str) -> Optional[Dict[str, Any]]:
    """Parse a Component's raw `options` JSON blob (`GraphStore`'s
    `record_component_options` field) and classify which of the three known
    shapes it is, returning a normalized `{"kind", ...}` dict, or `None` if
    empty/unparseable/unrecognized. The single place every consumer of this
    field (`graph_prd_synthesizer.py`'s catalog narration,
    `component_tree.py`'s deterministic renderer) goes to interpret it, so
    the three-shape disambiguation logic exists exactly once:

    - `{"kind": "stepper", "container", "increment_path", "decrement_path",
       "value_path", "current_value"}` - `group_steppers`' output, written by
      `GraphStoreSink.record_inventory`.
    - `{"kind": "choice_group", "group", "choices": [{"text", "selected"}]}`
      - `group_choice_sets`' output, same writer.
    - `{"kind": "revealed_options", "trigger", "choices": [{"text",
       "selected"}]}` - `find_revealed_options`' output, written by
      `GraphStoreSink.record_revealed_options` (Phase 1).
    """
    if not options_json:
        return None
    try:
        options = json.loads(options_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(options, dict):
        return None

    if "increment_path" in options and "decrement_path" in options:
        return {
            "kind": "stepper",
            "container": options.get("container"),
            "increment_path": options.get("increment_path"),
            "decrement_path": options.get("decrement_path"),
            "value_path": options.get("value_path"),
            "current_value": options.get("current_value"),
        }
    if "group" in options and "options" in options:
        return {
            "kind": "choice_group",
            "group": options["group"],
            "choices": [
                {"text": o.get("text"), "selected": bool(o.get("selected"))}
                for o in options.get("options", [])
            ],
        }
    if "trigger" in options and "revealed_options" in options:
        return {
            "kind": "revealed_options",
            "trigger": options.get("trigger"),
            "choices": [
                {"text": o.get("text"), "selected": bool(o.get("selected"))}
                for o in options.get("revealed_options", [])
            ],
        }
    return None
