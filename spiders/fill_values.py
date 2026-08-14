"""Deterministic fill-value generation for mechanically-discovered form fields.
Details: docs/dev/spiders/fill_values.md#module
"""
from __future__ import annotations

from typing import Any, Dict


async def default_placeholder_fill_value(component: Dict[str, Any], page_description: str = "") -> str:
    """Non-AI placeholder fill value - Phase 2 default and Phase 4 fallback.
    Details: docs/dev/spiders/fill_values.md#default_placeholder_fill_value
    """
    input_type = component.get("input_type", "")
    if input_type == "email":
        return "test@example.com"
    if input_type == "number":
        return "1"
    if input_type == "url":
        return "https://example.com"
    if input_type == "tel":
        return "555-0100"
    return "test"
