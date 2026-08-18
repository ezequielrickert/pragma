"""Translate this project's captured "shape" language into JSON Schema.

The shape language is what `network_filter._json_shape` produces and
`database/ladybug/network.py::_merge_shape` unions: a JSON document with every value
replaced by its type name, and a trailing `?` on any key that some
observed samples were missing. It exists so a request body can be
described without ever persisting a real value.

JSON Schema is what OpenAPI needs. This module is the only place that
knows both, so neither the capture side nor the document side has to.

Details: docs/dev/generators/json_schema.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

# Shape type name -> JSON Schema type. `"null"` has no JSON Schema type of
# its own in OpenAPI 3.0, which spells it as a nullable schema instead.
# Details: docs/dev/generators/json_schema.md#_scalar_schemas
_SCALAR_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "string": {"type": "string"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "null": {"nullable": True},
}

# Marks a key that some samples of the same endpoint didn't carry.
_OPTIONAL_SUFFIX = "?"


def _split_optional(type_name: str) -> Tuple[str, bool]:
    """`("string", True)` for `"string?"`, `("string", False)` otherwise."""
    if type_name.endswith(_OPTIONAL_SUFFIX):
        return type_name[: -len(_OPTIONAL_SUFFIX)], True
    return type_name, False


def _schema_for(shape: Any) -> Dict[str, Any]:
    """One shape node to one JSON Schema node, recursively."""
    if isinstance(shape, dict):
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for key, value in shape.items():
            if isinstance(value, str):
                type_name, optional = _split_optional(value)
                properties[key] = dict(_SCALAR_SCHEMAS.get(type_name, {}))
            else:
                optional = False
                properties[key] = _schema_for(value)
            if not optional:
                required.append(key)
        schema: Dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema
    if isinstance(shape, list):
        # A one-element list is how _json_shape represents a homogeneous
        # array; an empty one is an array whose element type was never seen.
        return {"type": "array", "items": _schema_for(shape[0]) if shape else {}}
    if isinstance(shape, str):
        type_name, _ = _split_optional(shape)
        return dict(_SCALAR_SCHEMAS.get(type_name, {}))
    return {}


def schema_from_shape(shape_json: str) -> Dict[str, Any]:
    """JSON Schema for one captured shape.

    Args:
        shape_json: a JSON-encoded shape, e.g.
            `'{"sku": "string", "note": "string?"}'`. `""` for a body that
            was never JSON (a form submit, an empty GET).

    Returns:
        `{}` when there is no shape to describe - an empty schema means
        "anything", which is the honest answer when nothing was observed,
        and it keeps the caller from having to special-case the absence.
        Otherwise a JSON Schema object: keys marked `?` are omitted from
        `required`, nested objects and arrays recurse, and a type name
        this module doesn't know maps to `{}` rather than raising, since
        the shape language is produced upstream and may gain a name before
        this module hears about it.
    Details: docs/dev/generators/json_schema.md#schema_from_shape
    """
    if not shape_json:
        return {}
    try:
        shape = json.loads(shape_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    return _schema_for(shape)
