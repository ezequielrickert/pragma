"""D14/`data-model.json`: what the application collects, deduced from the
forms it shows, per docs/adr/0008.

The semantic tier's first inhabitant. Everything above it in the schema -
`observation`, `inferred` - records what the crawl saw or clustered; this
records what the application *means*, which is a different kind of claim and
is why every node it writes carries `DERIVED_FROM` edges back to the
components that support it.

**Entities are still forms-only, and that is a schema constraint rather
than a preference.** `DERIVED_FROM` declares `FROM Entity TO Component`
and `FROM Field TO Component`, with no pair reaching a `Request` -
naming a *new* entity purely from an API body shape (with no form
`id`/context) is exactly the kind of guess this tier can't show its work
for. Since ticket #103, an *existing* form-derived field's
`observed_in.api_endpoints` (ADR-0008 point 2) is correlated against API
traffic anyway - a document-generation-time computation, not a graph
write, so it needs no `DERIVED_FROM` edge and no migration to the write
path this docstring used to say API correlation was blocked on. This is
what fixes the format audit's own complaint (ADR-0008's intro): a field
present in API traffic but unexposed in the HTML form was undercounted
before.

Pure and deterministic, no model call: `build_entities` maps components to
entities and nothing else. Naming a form's noun ("this is a Checkout") is
exactly the kind of guess this tier is supposed to be able to show its work
for, and it cannot, so it is not attempted.

Details: docs/dev/generators/data_model.md#module
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.interfaces import SemanticEntity, SemanticField
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from .ledger import flat_component_ledger

_SCHEMA_PATH = "schemas/data-model.schema.json"

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


def group_form_components(components: Sequence[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """`{(page_url, form_selector): [component, ...]}` - the grouping
    `build_entities` turns into `SemanticEntity`/`SemanticField` objects
    and `build_data_model_document` (docs/adr/0008) reads directly, since
    the JSON assembly needs the raw `form_selector` a `SemanticEntity`'s
    own `description` only carries as prose.
    Details: docs/dev/generators/data_model.md#group_form_components
    """
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for component in components:
        form_selector = (component.get("form") or "").strip()
        if not form_selector or not _is_field(component):
            continue
        if not _field_name(component):
            continue
        grouped.setdefault((component.get("page_url", ""), form_selector), []).append(component)
    return grouped


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
    entities = []
    for (page_url, form_selector), members in sorted(group_form_components(components).items()):
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


# Field-name substrings mapped onto a W3C DPV category/type and a
# sensitivity default - a small, stated heuristic (ADR-0008 point 1),
# not an exhaustive privacy audit. False negatives (a PII field this
# table misses) are the safe failure mode; the signal list stays narrow
# and specific rather than broad, to avoid a false positive flagging an
# unrelated field as personal data.
# Details: docs/dev/generators/data_model.md#_pii_signals
_PII_SIGNALS: Tuple[Tuple[Tuple[str, ...], str, str, str], ...] = (
    (("email",), "dpv:PersonalData", "dpv:EmailAddress", "medium"),
    (("password", "pwd", "passwd"), "dpv:PersonalData", "dpv:Credential", "high"),
    (("phone", "tel", "mobile"), "dpv:PersonalData", "dpv:PersonalIdentifier", "medium"),
    (("card", "cvv", "cvc", "creditcard"), "dpv:PersonalData", "dpv:FinancialData", "high"),
    (("ssn", "dni", "passport", "nationalid", "taxid"), "dpv:PersonalData", "dpv:PersonalIdentifier", "high"),
    (("address", "street", "zipcode", "postalcode"), "dpv:PersonalData", "dpv:Location", "medium"),
    (("firstname", "lastname", "fullname", "surname"), "dpv:PersonalData", "dpv:Name", "low"),
    (("dob", "birthdate", "dateofbirth"), "dpv:PersonalData", "dpv:Age", "medium"),
)


def _privacy_annotation(field_name: str) -> Optional[Dict[str, Any]]:
    """`None` for a field this heuristic has no opinion about - absent
    from the document entirely, never a false `is_pii: false` presented
    as a real finding.
    Details: docs/dev/generators/data_model.md#_privacy_annotation
    """
    normalized = re.sub(r"[^a-z]", "", field_name.lower())
    for signals, category, dpv_type, sensitivity in _PII_SIGNALS:
        if any(signal in normalized for signal in signals):
            return {"is_pii": True, "category": category, "dpv_type": dpv_type, "sensitivity": sensitivity}
    return None


# SemanticField.data_type -> (JSON Schema type, format) - "" format means
# the bare type carries the whole story.
_JSON_SCHEMA_TYPE: Dict[str, Tuple[str, str]] = {
    "string": ("string", ""), "number": ("number", ""), "boolean": ("boolean", ""),
    "date": ("string", "date"), "email": ("string", "email"), "tel": ("string", "tel"),
    "url": ("string", "uri"),
}


def _api_citations(field_name: str, inferred_requests: Sequence[Any]) -> Tuple[str, ...]:
    """Every endpoint whose observed request or response body carries a
    key matching `field_name` - the fix for the format audit's own
    complaint (ADR-0008's intro): fields present in API traffic but
    unexposed in HTML forms were undercounted before this. No graph
    schema change needed for it - `DERIVED_FROM` still only reaches a
    `Component` (see this module's own docstring), but this citation is
    computed at document-generation time, entirely independent of that
    write-path constraint.
    Details: docs/dev/generators/data_model.md#_api_citations
    """
    normalized = field_name.strip().lower()
    citations = []
    for request in inferred_requests:
        for shape in (request.body_shape, request.response_shape):
            if not shape:
                continue
            try:
                keys = json.loads(shape).keys()
            except (json.JSONDecodeError, AttributeError):
                continue
            if any(key.lower() == normalized for key in keys):
                citations.append(f"{request.method} {request.endpoint}")
                break
    return tuple(sorted(set(citations)))


def _observed_in(
    field: SemanticField, form_selector: str, inferred_requests: Sequence[Any]
) -> Dict[str, List[str]]:
    return {
        "forms": [f"{form_selector} input[name='{field.name}']"],
        "api_endpoints": list(_api_citations(field.name, inferred_requests)),
        "ui_state": sorted({f"SCR-{short_hash(page_url)}" for page_url, _ in field.derived_from}),
    }


def _confidence(observed_in: Dict[str, List[str]]) -> float:
    """A stated, deliberately simple v1 heuristic (matching `openapi.yaml`'s
    own `x-inference.confidence`, docs/adr/0004): 0.7 for a form-declared
    field alone, +0.2 when API traffic corroborates it, +0.1 when it
    recurs across more than one screen.
    Details: docs/dev/generators/data_model.md#_confidence
    """
    score = 0.7
    if observed_in["api_endpoints"]:
        score += 0.2
    if len(observed_in["ui_state"]) > 1:
        score += 0.1
    return round(min(1.0, score), 2)


def _field_document(field: SemanticField, form_selector: str, inferred_requests: Sequence[Any]) -> Dict[str, Any]:
    json_type, json_format = _JSON_SCHEMA_TYPE.get(field.data_type, ("string", ""))
    observed_in = _observed_in(field, form_selector, inferred_requests)
    document: Dict[str, Any] = {
        "type": json_type, "nullable": not field.required,
        "confidence": _confidence(observed_in), "observed_in": observed_in,
    }
    if json_format:
        document["format"] = json_format
    privacy = _privacy_annotation(field.name)
    if privacy:
        document["privacy"] = privacy
    return document


def _gaps(coverage: Any, run_id: str) -> List[Dict[str, Any]]:
    """One gap per unfinished page (docs/adr/0008 point 3) - `entity`
    names the page itself, since no form-derived name exists for a page
    the crawl never reached. `unvisited_endpoint` reuses `coverage.json`'s
    own page-level gap data (`coverage.unfinished_urls`): pragma has no
    way to detect a genuinely unvisited *API endpoint* it never observed
    a link or reference to, unlike an unfinished page, which the crawl
    frontier already tracks.
    Details: docs/dev/generators/data_model.md#_gaps
    """
    if coverage is None:
        return []
    return [
        {
            "entity": url, "reason": "unvisited_route",
            "coverage_ref": {"run_id": run_id, "unvisited_endpoint": url},
        }
        for url in coverage.unfinished_urls
    ]


def build_data_model_document(request: DocumentRequest) -> Dict[str, Any]:
    """The full `data-model.json` payload: one entity per form
    (`group_form_components`), each field annotated with multi-source
    provenance and, where a naming heuristic matched, a DPV privacy
    object - plus the coverage gaps this crawl left.
    Details: docs/dev/generators/data_model.md#build_data_model_document
    """
    components = flat_component_ledger(request.graph_store)
    inferred_requests = request.graph_store.get_inferred_requests()
    run_id = request.settings.get("run_id", "")

    entities: Dict[str, Any] = {}
    for (page_url, form_selector), members in sorted(group_form_components(components).items()):
        fields = sorted({_field_name(member) for member in members if _field_name(member)})
        field_by_name = {_field_name(member): member for member in members}
        semantic_fields = [
            SemanticField(
                name=name,
                data_type=_DATA_TYPES.get((field_by_name[name].get("input_type") or "").lower(), "string"),
                required=bool(field_by_name[name].get("required")),
                validation=_validation(field_by_name[name]),
                observed_values=_observed_values(field_by_name[name]),
                derived_from=((page_url, field_by_name[name].get("path", "")),),
            )
            for name in fields
        ]
        entity_name = _entity_name(form_selector, page_url)
        entities[entity_name] = {
            "description": f"Deduced from the form `{form_selector}` on {page_url}.",
            "fields": {
                field.name: _field_document(field, form_selector, inferred_requests) for field in semantic_fields
            },
        }

    return {"entities": entities, "gaps": _gaps(request.coverage, run_id)}


def _mermaid_identifier(name: str) -> str:
    """A Mermaid-safe identifier - alphanumeric and underscore only, since
    `erDiagram` entity/attribute names don't tolerate the punctuation a
    form `id` or a field `name` can carry.
    Details: docs/dev/generators/data_model.md#_mermaid_identifier
    """
    return re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "field"


def _mermaid_er_diagram(document: Dict[str, Any]) -> str:
    """A native Markdown Mermaid `erDiagram` block (docs/adr/0008 point 4)
    - one entity block per form, no relationship lines: pragma's forms
    are independent, unrelated by anything the crawl observed, and
    drawing a connection between them would be a guess this document
    doesn't make anywhere else.
    Details: docs/dev/generators/data_model.md#_mermaid_er_diagram
    """
    lines = ["```mermaid", "erDiagram"]
    for entity_name, entity in document["entities"].items():
        lines.append(f"    {_mermaid_identifier(entity_name)} {{")
        for field_name, field in entity["fields"].items():
            lines.append(f"        {field['type']} {_mermaid_identifier(field_name)}")
        lines.append("    }")
    lines.append("```")
    return "\n".join(lines)


def _entity_section(entity_name: str, entity: Dict[str, Any]) -> List[str]:
    lines = [
        f"## {entity_name}", "", entity["description"], "",
        "| Field | Type | Nullable | Confidence | PII | Observed in |",
        "|---|---|---|---|---|---|",
    ]
    for field_name, field in entity["fields"].items():
        json_type = f"{field['type']} ({field['format']})" if field.get("format") else field["type"]
        privacy = field.get("privacy")
        pii = f"{privacy['dpv_type']} ({privacy['sensitivity']})" if privacy else "-"
        sources = [
            f"{len(field['observed_in'][key])} {label}"
            for key, label in (("forms", "form(s)"), ("api_endpoints", "endpoint(s)"), ("ui_state", "screen(s)"))
            if field["observed_in"][key]
        ]
        lines.append(
            f"| {field_name} | {json_type} | {'yes' if field['nullable'] else 'no'} "
            f"| {field['confidence']} | {pii} | {', '.join(sources) or '-'} |"
        )
    lines.append("")
    return lines


def _gaps_section(gaps: List[Dict[str, Any]]) -> List[str]:
    if not gaps:
        return []
    lines = [
        "## Coverage gaps", "",
        f"{len(gaps)} page(s) the crawl never finished - any entity they would have revealed is "
        "absent above, not confirmed absent.",
        "", "| Page | Run |", "|---|---|",
    ]
    lines += [f"| {gap['entity']} | {gap['coverage_ref']['run_id']} |" for gap in gaps]
    return lines + [""]


def _render_data_model_view(document: Dict[str, Any], site: str) -> str:
    """`data-model.md` - mechanically rendered from `data-model.json`,
    never hand-authored in parallel with it.
    Details: docs/dev/generators/data_model.md#_render_data_model_view
    """
    lines = [f"# Data Model: {site}", ""]
    if not document["entities"]:
        lines.append(
            "No forms with named inputs were found. Either the crawl reached no form, or the "
            "inputs it found carry no `name`, label or placeholder to identify them - the two "
            "look the same here."
        )
        return "\n".join(lines) + "\n"
    lines += [
        f"{len(document['entities'])} form(s). Names are the form's own `id` where it has one, "
        "never a noun guessed from the fields: a form asking for an email and a password could be "
        "a login, a signup or an invite, and this document has no way to show its work for that "
        "choice.",
        "", _mermaid_er_diagram(document), "",
    ]
    for entity_name, entity in document["entities"].items():
        lines += _entity_section(entity_name, entity)
    lines += _gaps_section(document["gaps"])
    return "\n".join(lines)


@DOCUMENT_REGISTRY.register("data-model")
class DataModelDocument(DocumentGenerator):
    """`data-model.json` (source, schema-validated) and `data-model.md`
    (view, with a native Mermaid `erDiagram`) - docs/adr/0008.
    Details: docs/dev/generators/data_model.md#datamodeldocument
    """

    name = "data-model"
    title = "Data Model"
    purpose = "What the application collects, deduced from its forms, with DPV privacy annotations and multi-source provenance."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        document = build_data_model_document(request)
        validate_against_schema(document, _SCHEMA_PATH)
        source = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        view = _render_data_model_view(document, request.site)
        return (
            DocumentOutput(filename="data-model", kind="source", extension="json", content=source),
            DocumentOutput(filename="data-model", kind="view", extension="md", content=view),
        )
