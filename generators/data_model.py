"""D14: what the application collects, deduced from the forms it shows.

The semantic tier's first inhabitant. Everything above it in the schema -
`observation`, `inferred` - records what the crawl saw or clustered; this
records what the application *means*, which is a different kind of claim and
is why every node it writes carries `DERIVED_FROM` edges back to the
components that support it.

**Forms only, and that is a schema constraint rather than a preference.**
`DERIVED_FROM` declares `FROM Entity TO Component` and `FROM Field TO
Component`, with no pair reaching a `Request`. An entity deduced from an API
body shape therefore could not record where it came from, and the rule this
tier exists to uphold is that nothing enters without provenance. Deriving
those too means adding a pair to that table, which existing `.lbdb` files
would not pick up - `CREATE REL TABLE IF NOT EXISTS` does not alter an
existing one - so it needs a migration story, not a line of DDL. Until then
the API side of the model lives in D4, which describes it honestly as shapes.

Pure and deterministic, no model call: `build_entities` maps components to
entities and nothing else. Naming a form's noun ("this is a Checkout") is
exactly the kind of guess this tier is supposed to be able to show its work
for, and it cannot, so it is not attempted.

Details: docs/dev/generators/data_model.md#module
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.interfaces import SemanticEntity, SemanticField
from core.registry import DOCUMENT_REGISTRY
from .ledger import flat_component_ledger

# Declared input types mapped onto the vocabulary `SemanticField.data_type`
# uses. Anything unlisted stays a string: the point is to report what the
# markup declares, not to normalise it into something tidier than it is.
# Details: docs/dev/generators/data_model.md#_data_types
_DATA_TYPES: Dict[str, str] = {
    "number": "number", "range": "number",
    "checkbox": "boolean", "radio": "boolean",
    "date": "date", "datetime-local": "date", "month": "date", "week": "date", "time": "date",
    "email": "email", "tel": "tel", "url": "url",
}

# Component types that ask a user for a value. A button is part of a form and
# is not a field of the entity the form collects.
# Details: docs/dev/generators/data_model.md#_field_types
_FIELD_TYPE_PREFIXES = ("text field", "checkbox", "radio", "combobox", "dropdown", "select", "textarea")


def _is_field(component: Dict[str, Any]) -> bool:
    component_type = (component.get("component_type") or "").lower()
    return any(component_type.startswith(prefix) for prefix in _FIELD_TYPE_PREFIXES)


def _field_name(component: Dict[str, Any]) -> str:
    """What the application calls this input, or `""` if nothing does.

    `name` first because it is what the application itself uses when it
    submits; label and placeholder are what it shows a person. A field with
    none of the three is dropped by `build_entities` rather than emitted
    under an invented name.
    Details: docs/dev/generators/data_model.md#_field_name
    """
    for key in ("name", "label", "placeholder"):
        value = (component.get(key) or "").strip()
        if value:
            return value
    return ""


def _validation(component: Dict[str, Any]) -> str:
    """What the markup declares about acceptable values, in prose.

    Only what is declared. Inferring a rule from the values a crawl happened
    to submit ("always 4 digits") would be a guess dressed as a constraint,
    and this tier is the one place in the project where that distinction is
    load-bearing.
    Details: docs/dev/generators/data_model.md#_validation
    """
    declared = []
    input_type = (component.get("input_type") or "").strip()
    if input_type and input_type not in ("text", ""):
        declared.append(f"type={input_type}")
    if component.get("required"):
        declared.append("required")
    return ", ".join(declared)


def _observed_values(component: Dict[str, Any]) -> Tuple[str, ...]:
    values = {
        (interaction.get("value") or "").strip()
        for interaction in component.get("interactions") or []
        if interaction.get("action") == "fill" and (interaction.get("value") or "").strip()
    }
    return tuple(sorted(values))


def _entity_name(form_selector: str, page_url: str) -> str:
    """A form's identity, from its `id` where it has one.

    Falls back to the page's last path segment, which is the only other
    thing captured that carries intent. Deliberately never a noun invented
    from the field names: a form with `email` and `password` might be a
    login, a signup or an invite, and this tier has no way to show its work
    for that choice.
    Details: docs/dev/generators/data_model.md#_entity_name
    """
    element_id = re.search(r"#([A-Za-z0-9_-]+)", form_selector or "")
    if element_id:
        return element_id.group(1)
    segments = [segment for segment in (page_url or "").rstrip("/").split("/") if segment]
    return f"{segments[-1]} form" if segments else "form"


def build_entities(components: Sequence[Dict[str, Any]]) -> List[SemanticEntity]:
    """One `SemanticEntity` per form the crawl found inputs inside.

    Grouped by `(page_url, facts.form)`: `form` is `el.closest('form')`'s
    selector, recorded by discovery, so two forms on one page stay two
    entities and the same form seen on two pages stays two - a form is a
    thing on a page, and merging by name across pages would assert an
    identity nothing in the data supports.

    Inputs outside any form are skipped. A lone search box is not an entity,
    and treating every stray input as one produces a document of noise.
    Details: docs/dev/generators/data_model.md#build_entities
    """
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for component in components:
        form_selector = (component.get("form") or "").strip()
        if not form_selector or not _is_field(component):
            continue
        if not _field_name(component):
            continue
        grouped.setdefault((component.get("page_url", ""), form_selector), []).append(component)

    entities = []
    for (page_url, form_selector), members in sorted(grouped.items()):
        fields = tuple(sorted(
            (
                SemanticField(
                    name=_field_name(member),
                    data_type=_DATA_TYPES.get((member.get("input_type") or "").lower(), "string"),
                    required=bool(member.get("required")),
                    validation=_validation(member),
                    observed_values=_observed_values(member),
                    derived_from=((page_url, member.get("path", "")),),
                )
                for member in members
            ),
            key=lambda field: field.name,
        ))
        entities.append(
            SemanticEntity(
                name=_entity_name(form_selector, page_url),
                description=f"Deduced from the form `{form_selector}` on {page_url}.",
                fields=fields,
                derived_from=tuple(sorted((page_url, member.get("path", "")) for member in members)),
            )
        )
    return entities


def _entity_section(entity: SemanticEntity) -> List[str]:
    lines = [
        f"## {entity.name}",
        "",
        entity.description,
        "",
        "| Field | Type | Required | Declared validation | Values the crawl submitted |",
        "|---|---|---|---|---|",
    ]
    for field in entity.fields:
        values = ", ".join(f"`{value}`" for value in field.observed_values) or "-"
        lines.append(
            f"| {field.name} | {field.data_type} | {'yes' if field.required else 'no'} "
            f"| {field.validation or '-'} | {values} |"
        )
    lines.append("")
    lines.append(
        "Derived from: " + ", ".join(f"`{path}` on {page}" for page, path in entity.derived_from) + "."
    )
    lines.append("")
    return lines


@DOCUMENT_REGISTRY.register("data-model")
class DataModelDocument(DocumentGenerator):
    """Details: docs/dev/generators/data_model.md#datamodeldocument"""

    name = "data-model"
    title = "Data Model"
    purpose = "What the application collects, deduced from its forms, with the elements each field came from."

    def generate(self, request: DocumentRequest) -> str:
        entities = build_entities(flat_component_ledger(request.graph_store))
        lines = [f"# Data Model: {request.site}", ""]
        if not entities:
            lines += [
                "No forms with named inputs were found. Either the crawl reached no form, or the "
                "inputs it found carry no `name`, label or placeholder to identify them - the two "
                "look the same here.",
                "",
            ]
            return "\n".join(lines)
        lines += [
            f"{len(entities)} form(s), each with the elements it was derived from. Names are the "
            "form's own `id` where it has one, never a noun guessed from the fields: a form asking "
            "for an email and a password could be a login, a signup or an invite, and this "
            "document has no way to show its work for that choice.",
            "",
            "Types and validation are what the **markup declares**. A field named for an email but "
            "declared as plain text reads as a string here, and the usability audit reports the "
            "gap - correcting it silently would hide that finding.",
            "",
        ]
        for entity in entities:
            lines += _entity_section(entity)
        return "\n".join(lines)
