"""Component-identity and interaction-target matching for the mechanical
crawl loop. Details: docs/dev/spiders/component_matching.md#module
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

# "type into" vs "click" target tags/input_types.
# Details: docs/dev/spiders/component_matching.md#fillable_input_types
FILLABLE_INPUT_TYPES = {"", "text", "email", "search", "tel", "url", "number", "password"}


def is_element_not_found(exc: Exception) -> bool:
    """Whether `exc` is crawl4ai_crawler.py's specific "selector didn't
    resolve" failure. Details: docs/dev/spiders/component_matching.md#is_element_not_found
    """
    return "element not found" in str(exc).lower()


def component_identity(component: Dict[str, Any]) -> tuple:
    """Content-based identity, stable across a DOM remount that reassigns ids.
    Details: docs/dev/spiders/component_matching.md#component_identity
    """
    return (
        component.get("tag", ""),
        component.get("role", ""),
        component.get("name", ""),
        component.get("form", ""),
        component.get("text", ""),
    )


def component_signature(components: List[Dict[str, Any]]) -> str:
    """Order-independent shape fingerprint of a *visible* component snapshot.
    Details: docs/dev/spiders/component_matching.md#component_signature
    """
    identities = sorted(component_identity(c) for c in components if c.get("visible"))
    return hashlib.sha1(repr(identities).encode("utf-8")).hexdigest()[:10]


def state_transition_key(page_key: str, components: List[Dict[str, Any]]) -> str:
    """Canonical GraphStore/tracker key for an in-page state reached without
    any URL change. Details: docs/dev/spiders/component_matching.md#state_transition_key
    """
    return f"{page_key}#state:{component_signature(components)}"


def component_overlap_ratio(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> float:
    """Fraction of `before`'s visible components still present in `after`.
    Details: docs/dev/spiders/component_matching.md#component_overlap_ratio
    """
    before_identities = {component_identity(c) for c in before if c.get("visible")}
    if not before_identities:
        return 1.0
    after_identities = {component_identity(c) for c in after if c.get("visible")}
    return len(before_identities & after_identities) / len(before_identities)


def remap_stale_frontier(
    remaining: List[Dict[str, Any]], fresh_components: List[Dict[str, Any]]
) -> "tuple[List[Dict[str, Any]], List[str]]":
    """Reconcile not-yet-attempted frontier items against a fresh DOM snapshot.
    Details: docs/dev/spiders/component_matching.md#remap_stale_frontier
    """
    fresh_paths = {c.get("path") for c in fresh_components}
    identity_map: Dict[tuple, str] = {}
    for c in fresh_components:
        identity_map.setdefault(component_identity(c), c.get("path"))

    remapped: List[Dict[str, Any]] = []
    dropped: List[str] = []
    for component in remaining:
        path = component.get("path")
        if path in fresh_paths:
            remapped.append(component)
            continue
        new_path = identity_map.get(component_identity(component))
        if new_path:
            updated = dict(component)
            updated["path"] = new_path
            remapped.append(updated)
        else:
            dropped.append(path)
    return remapped, dropped


def is_fillable(component: Dict[str, Any]) -> bool:
    tag = component.get("tag", "")
    if tag == "textarea":
        return True
    if tag == "select":
        return True
    if tag == "input":
        return component.get("input_type", "") in FILLABLE_INPUT_TYPES
    return False
