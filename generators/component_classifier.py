"""Deterministic component classification and grouping for the PRD narration pass.
Details: docs/dev/generators/component_classifier.md#module
"""
from __future__ import annotations

import json
import unicodedata
from typing import Any, Dict, List, Optional

# role values marking a member of an enumerable list (dropdown/combobox/menu).
_OPTION_ROLES = {"option", "menuitem", "menuitemcheckbox", "menuitemradio", "tab"}

# Same list-member roles, minus "tab": for storage-node consolidation
# (group_option_families) tabs are deliberately excluded even though they
# share option-family markup, because each tab usually gates materially
# different page content and stays worth tracking as its own component -
# unlike a dropdown/menu's choices, which really are one list.
_LIST_MEMBER_ROLES = {"option", "menuitem", "menuitemcheckbox", "menuitemradio"}

# Increment/decrement vocabulary, English + Spanish (matched after normalize()).
_INCREMENT_WORDS = {"agregar", "sumar", "mas", "add", "increase", "increment", "plus", "+"}
_DECREMENT_WORDS = {"restar", "quitar", "menos", "remove", "decrease", "decrement", "minus", "-"}


def _normalize(text: str) -> str:
    """Lowercase, accent-stripped comparison key for vocabulary matching."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return text.strip().lower()


def classify_component_type(comp: Dict[str, Any]) -> str:
    """A short, human-readable type label from tag/role/input_type alone.
    Details: docs/dev/generators/component_classifier.md#classify_component_type
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
    """Option-family components a trigger's click/fill just made available.
    Details: docs/dev/generators/component_classifier.md#find_revealed_options
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
    """CSS path of `path`'s immediate parent, used as a sibling-grouping key."""
    segments = (path or "").split(" > ")
    return " > ".join(segments[:-1])


def _looks_numeric(text: str) -> bool:
    stripped = (text or "").strip()
    return bool(stripped) and any(ch.isdigit() for ch in stripped) and all(
        ch.isdigit() or ch in ".,+- " for ch in stripped
    )


def group_steppers(components: List[dict]) -> List[Dict[str, Any]]:
    """Detect increment/decrement button pairs sharing a common parent container.
    Details: docs/dev/generators/component_classifier.md#group_steppers
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
    """Radio/checkbox components sharing the same `name` attribute.
    Details: docs/dev/generators/component_classifier.md#group_choice_sets
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


def group_option_families(components: List[dict]) -> Dict[str, List[dict]]:
    """Option/menu-item components sharing an immediate parent - the DOM shape
    of a single dropdown or menu's list of choices (a native `<select>`'s
    `<option>`s never reach here at all; discovery never treats them as their
    own components in the first place - see discover_components.js).
    Details: docs/dev/generators/component_classifier.md#group_option_families
    """
    groups: Dict[str, List[dict]] = {}
    for comp in components:
        role = (comp.get("role") or "").lower()
        path = comp.get("path") or ""
        if role not in _LIST_MEMBER_ROLES or not path:
            continue
        groups.setdefault(_parent_path(path), []).append(comp)
    return {parent: members for parent, members in groups.items() if len(members) >= 2 and parent}


def describe_options(options_json: str) -> Optional[Dict[str, Any]]:
    """Parse a Component's raw `options` JSON blob into a normalized `{"kind", ...}` dict.
    Details: docs/dev/generators/component_classifier.md#describe_options
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
                {"path": o.get("path"), "text": o.get("text"), "selected": bool(o.get("selected"))}
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


def describe_options_from_rows(rows: List[Dict[str, Any]], group_name: str) -> Optional[Dict[str, Any]]:
    """`describe_options`'s counterpart for the real graph: the same
    normalized `{"kind", ...}` shape, built directly from `Option` rows
    (`database/ladybug/options.py`'s own write-side encoding, reversed)
    instead of parsing a JSON blob - there is no blob to parse anymore.

    Args:
        rows: one dict per `Option` a component's `HAS_OPTION` edges
            reach, each `{"path", "text", "selected"}`, in `seq` order.
        group_name: the `group_name` every one of those `Option`s shares -
            `"stepper"` (a reserved sentinel, see `options.py`'s module
            docstring for the four-role-tag encoding this decodes), or
            the group/trigger name for the other two kinds.

    Returns:
        `None` for an empty `rows`. Otherwise the same shape
        `describe_options` returns for each of its three kinds -
        distinguished the same way the write side did: `group_name ==
        "stepper"` first, then whether any row carries a real `path`
        (only ever true for `choice_group`; `revealed_options` rows
        never had a DOM selector of their own).
    Details: docs/dev/generators/component_classifier.md#describe_options_from_rows
    """
    if not rows:
        return None
    if group_name == "stepper":
        by_text = {r["text"]: r for r in rows if not r["text"].startswith("value:")}
        value_row = next((r for r in rows if r["text"].startswith("value:")), None)
        return {
            "kind": "stepper",
            "container": (by_text.get("container") or {}).get("path"),
            "increment_path": (by_text.get("increment") or {}).get("path"),
            "decrement_path": (by_text.get("decrement") or {}).get("path"),
            "value_path": value_row["path"] if value_row else None,
            "current_value": value_row["text"].partition(":")[2] if value_row else None,
        }
    if any(r.get("path") for r in rows):
        return {
            "kind": "choice_group", "group": group_name,
            "choices": [{"path": r["path"], "text": r["text"], "selected": r["selected"]} for r in rows],
        }
    return {
        "kind": "revealed_options", "trigger": group_name,
        "choices": [{"text": r["text"], "selected": r["selected"]} for r in rows],
    }


def format_option_choices(parsed: Optional[Dict[str, Any]]) -> List[str]:
    """Render `describe_options`' normalized shape as short, human-readable
    display strings - the same clean form the component-tree document
    shows (`variants=[Mi Gusto (selected), Solo Empanadas, ...]`), reused
    here so a Component's raw JSON `options` blob doesn't need external
    tooling to read; `graph_sink.py` computes this once per write and
    stores it as `option_labels` alongside the raw JSON.

    Args:
        parsed: `describe_options`' return value, or `None`.

    Returns:
        - `[]` if `parsed` is `None`, or its `"kind"` is none of the ones
          below (defensive - every `describe_options` result matches one).
        - For `"kind": "stepper"`: a single-element list, either
          `["stepper (current value: <value>)"]` when a value was found,
          or `["stepper"]` otherwise.
        - For `"kind": "choice_group"` or `"revealed_options"`: one
          string per choice with real text, `f"{text} (selected)"` for
          the currently-selected one(s), plain `text` for the rest -
          choices with no text at all are skipped, not rendered as an
          empty string.
    Details: docs/dev/generators/component_classifier.md#format_option_choices
    """
    if not parsed:
        return []
    if parsed["kind"] == "stepper":
        current_value = parsed.get("current_value")
        return [f"stepper (current value: {current_value})" if current_value else "stepper"]
    if parsed["kind"] in ("choice_group", "revealed_options"):
        out = []
        for choice in parsed["choices"]:
            text = choice.get("text")
            if not text:
                continue
            out.append(f"{text} (selected)" if choice.get("selected") else text)
        return out
    return []


def choice_text_by_path(parsed: Dict[str, Any]) -> Dict[str, str]:
    """A `describe_options`' `choice_group` result's choices, keyed by their
    own `path` - the lookup both `component_tree.py`'s
    `_build_option_redirects` and `graph_prd_synthesizer.py`'s
    `_choices_leading_elsewhere` need to turn a redirected interaction's raw
    `source_path` back into a human-readable choice label.
    Details: docs/dev/generators/component_classifier.md#choice_text_by_path
    """
    return {c["path"]: c.get("text") for c in parsed["choices"] if c.get("path")}
