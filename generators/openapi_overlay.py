"""Minimal OpenAPI Overlay Specification 1.0.0 applier - docs/adr/0004's
non-destructive redaction workflow: `openapi.raw.yaml`, an overlay of
redaction actions, applied to produce the public `openapi.yaml`.

Deliberately not a full JSONPath implementation. `redaction.overlay.yaml`
is hand-authored by whoever maintains pragma's own redaction rules - the
same "fixed for a rule-set version, not derived from any crawl" shape
`CONTEXT.md`'s Rule catalog entry already names - so this only needs to
resolve the path shapes a human actually writes for that purpose: dotted
keys, bracket-quoted keys (for a path template's own `/`, `{`, `}`), and
a `[*]` wildcard fan-out. No filter expressions, no array indices, no
recursive descent - adding a real JSONPath dependency for an overlay file
that ships empty by default would be more machinery than this v1 need
justifies.

Details: docs/dev/generators/openapi_overlay.md#module
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple

_SEGMENT = re.compile(r"\.(?P<dot>[A-Za-z0-9_]+)|\[\*\]|\['(?P<bracket>[^']*)'\]")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _segments(target: str) -> List[str]:
    """`target`'s path, one string per step - `"*"` for a wildcard.
    Raises `ValueError` on anything this subset doesn't parse, rather
    than silently matching nothing: an overlay action that never fires is
    a rule someone should know isn't working.
    Details: docs/dev/generators/openapi_overlay.md#_segments
    """
    if not target.startswith("$"):
        raise ValueError(f"overlay target must start with '$': {target!r}")
    steps = []
    position = 1
    while position < len(target):
        match = _SEGMENT.match(target, position)
        if not match:
            raise ValueError(f"unsupported overlay target syntax at {target[position:]!r} in {target!r}")
        steps.append(match.group("dot") or match.group("bracket") or "*")
        position = match.end()
    return steps


def _path_step(path: str, key: Any) -> str:
    """One more step of a concrete field path - dot form for an
    identifier-shaped key, bracket-quoted for anything else (a path
    template's own `/`, `{`, `}`), `[N]` for a list index. Mirrors
    `_segments`'s own dot-vs-bracket split so a concrete path a match
    resolves to reads like a target a maintainer could have hand-written.
    Details: docs/dev/generators/openapi_overlay.md#_path_step
    """
    if isinstance(key, int):
        return f"{path}[{key}]"
    if _IDENTIFIER.match(key):
        return f"{path}.{key}"
    return f"{path}['{key}']"


def _matches(node: Any, segments: List[str], path: str = "$") -> List[Tuple[str, Any, Any]]:
    """`[(field_path, container, key)]` for every location `segments`
    resolves to, walking from `node` - a wildcard fans out over every key
    of a dict or every index of a list at that level. `field_path` is the
    concrete path a match resolved to, never the wildcard template itself
    - `redaction_events` below is why this is threaded through even
    though `apply_overlay` only needs `container`/`key`.
    Details: docs/dev/generators/openapi_overlay.md#_matches
    """
    segment, rest = segments[0], segments[1:]
    if segment == "*":
        children = (
            node.items() if isinstance(node, dict)
            else enumerate(node) if isinstance(node, list)
            else ()
        )
        if not rest:
            return [(_path_step(path, key), node, key) for key, _ in children]
        results: List[Tuple[str, Any, Any]] = []
        for key, child in children:
            results.extend(_matches(child, rest, _path_step(path, key)))
        return results
    if not isinstance(node, dict) or segment not in node:
        return []
    step_path = _path_step(path, segment)
    if not rest:
        return [(step_path, node, segment)]
    return _matches(node[segment], rest, step_path)


def apply_overlay(document: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """`document` with every action in `overlay["actions"]` applied.

    Non-destructive: `document` is deep-copied first, never mutated in
    place, so the caller's own `openapi.raw.yaml` payload survives
    unchanged for its own write. Matches are applied in reverse per
    action so a wildcard removing several items from the same list
    doesn't shift the indices of matches still queued for deletion.
    Details: docs/dev/generators/openapi_overlay.md#apply_overlay
    """
    result = copy.deepcopy(document)
    for action in overlay.get("actions", []):
        segments = _segments(action["target"])
        for _, container, key in reversed(_matches(result, segments)):
            if action.get("remove"):
                del container[key]
            elif "update" in action:
                container[key] = action["update"]
    return result


def redaction_events(document: Dict[str, Any], overlay: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """`[(field_path, action)]` for every field `overlay`'s actions
    actually match against `document` - the same match set `apply_overlay`
    would redact, computed read-only against the pre-redaction document
    so a caller (`redaction_log.py`) can cite exactly which concrete
    field a rule touched, never the value that was there. An action whose
    target matches nothing this run contributes no event - a rule that
    never fires is not evidence redaction happened.
    Details: docs/dev/generators/openapi_overlay.md#redaction_events
    """
    events: List[Tuple[str, Dict[str, Any]]] = []
    for action in overlay.get("actions", []):
        segments = _segments(action["target"])
        events += [(field_path, action) for field_path, _, _ in _matches(document, segments)]
    return events
