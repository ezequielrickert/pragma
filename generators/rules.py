"""Rule derivation: one `SemanticRule` per declared single-field
constraint on a form's field-bearing `Component`s, plus one `SemanticRule`
per real `<select>`'s declared option set - per 'Research Rule provenance
split and statement granularity' (issue #190). `kind="declared"`,
`confidence=1.0` throughout: read straight off markup, no model call, no
human review. `kind="inferred"` is explicitly out of scope for this
tier's writer so far.

Grouped through `data_model.group_form_components` - the exact
field-membership filter `build_entities` itself uses - so every Rule's
`derived_from` component already has (or, in the same run, will have) a
`Field` reachable through `EDITS`; `database/ladybug/rule.py::record_rules`
resolves each Rule's own `GOVERNS(Rule->Field)` edge through that join.

Pure and deterministic, no model call: a markup attribute is either
declared or it isn't, nothing here needs judgment.

Details: docs/dev/generators/rules.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from core.interfaces import SemanticRule
from generators.component_classifier import describe_options_from_rows
from generators.data_model import group_form_components

_KIND = "declared"
_CONFIDENCE = 1.0

# Numeric/length/pattern constraints beyond type/required - this ticket's
# own capture addition (spiders/content/js/discover_components.js +
# core/data_contracts.py::ComponentFacts), read the same declared-only
# way `data_model.py::_validation` already reads type/required.
_CONSTRAINT_ATTRIBUTES: Tuple[str, ...] = ("pattern", "min", "max", "minlength", "maxlength", "step")


def _declared_constraints(component: Dict[str, Any]) -> List[str]:
    """Every declared single-value constraint on one field, as terse
    `key=value` statements (or the bare `"required"`) - mirroring
    `data_model.py::_validation`'s own convention, one row here per
    constraint rather than that function's single combined string.
    Details: docs/dev/generators/rules.md#_declared_constraints
    """
    statements = []
    input_type = (component.get("input_type") or "").strip()
    if input_type and input_type not in ("text", ""):
        statements.append(f"type={input_type}")
    if component.get("required"):
        statements.append("required")
    for attribute in _CONSTRAINT_ATTRIBUTES:
        value = (component.get(attribute) or "").strip()
        if value:
            statements.append(f"{attribute}={value}")
    return statements


def _option_set_statement(component: Dict[str, Any]) -> str:
    """`"one of: [a, b, c]"` for a real `<select>`'s declared option set,
    else `""`.

    Scoped to `tag == "select"` and the `choice_group` `Option` shape -
    a JS-driven combobox's revealed choices are runtime state observed
    by a click, not markup this tier can call declared, and a native
    `<select>`'s own `<option>` children are not discovered as separate
    components at all today (`component_classifier.py::group_option_
    families`'s own docstring), so most real selects yield no rows here
    and no Rule - honest under this tier's "only what is captured"
    rule, not a bug in this derivation.
    Details: docs/dev/generators/rules.md#_option_set_statement
    """
    if (component.get("tag") or "").lower() != "select":
        return ""
    rows, group_name = component.get("options") or ([], "")
    parsed = describe_options_from_rows(rows, group_name)
    if parsed is None or parsed["kind"] != "choice_group":
        return ""
    texts = [choice["text"] for choice in parsed["choices"] if choice.get("text")]
    return f"one of: [{', '.join(texts)}]" if texts else ""


def _rules_for_component(component: Dict[str, Any]) -> List[SemanticRule]:
    derived_from = (component.get("page_url", ""), component.get("path", ""))
    statements = _declared_constraints(component)
    option_set = _option_set_statement(component)
    if option_set:
        statements.append(option_set)
    return [
        SemanticRule(statement=statement, kind=_KIND, confidence=_CONFIDENCE, derived_from=derived_from)
        for statement in statements
    ]


def build_rules(components: Sequence[Dict[str, Any]]) -> List[SemanticRule]:
    """One `SemanticRule` per declared constraint on every form field the
    crawl found, plus one per real `<select>`'s declared option set.

    Args:
        components: `ledger.flat_component_ledger` output, the same
            argument `build_entities` itself takes.

    Returns:
        Sorted by `(derived_from, statement)` for reproducible output.
        Every field-bearing `Component` `group_form_components` selects
        is walked once, so a component with no declared constraint at
        all (a plain, unconstrained text field) contributes no rows.
    Details: docs/dev/generators/rules.md#build_rules
    """
    rules = [
        rule
        for members in group_form_components(components).values()
        for component in members
        for rule in _rules_for_component(component)
    ]
    return sorted(rules, key=lambda rule: (rule.derived_from, rule.statement))
