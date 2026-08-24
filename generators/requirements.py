"""`requirements.json` + `prd.md`, per docs/adr/0009 - EARS-syntax
requirements extracted from the crawl graph, replacing the retired
LLM-narrated "Digital Blueprint" (`graph_prd_synthesizer.py`) entirely.
Fully deterministic, no model call anywhere - the same "generate-time
correlation over invented narration" discipline every other document in
this pipeline settled on.

**What each EARS pattern is derived from, and what stays reserved.**
`event_driven` and `ubiquitous` come from `InferredRequest.triggered_by`/
`.loaded_by` - real observed network traffic (`confidence: "observed"`).
`unwanted_behavior` comes from an observed failure status code - also
`"observed"`. `optional_feature` comes from `data-model.json`'s own
`nullable` fields - a declared-markup heuristic, so `"inferred"`, not
`"observed"`. A second, `ubiquitous`-pattern batch comes from
`SemanticRule` (`database/ladybug/rule.py`, issue #193) - a declared
markup constraint (`required`, `min=18`, ...) whose `GOVERNS` edge
resolved to a real `Field`/`Entity` - also `"inferred"`, the same
declared-markup-not-observed-traffic split `optional_feature` draws;
`Rule.kind="inferred"` rows (cross-field logic, human-reviewed) stay out
of scope here per #190/#193, and none exist yet regardless. `state_driven`
stays unused: pragma has no state-detection instrumentation (the same gap
`coverage.json`'s own UI-state dimension dropped, docs/adr/0001), so
nothing here can back a WHILE-clause honestly. `confidence: "assumed"` is
never emitted either - pragma has no extraction rule based on convention
rather than observation.

Details: docs/dev/generators/requirements.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.graph_metrics import build_screen_graph, compute_graph_metrics
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from utils.urls import route_shape
from .data_model import build_data_model_document

_SCHEMA_PATH = "schemas/requirements.schema.json"

_NO_LINKS: Dict[str, List[str]] = {"screens": [], "endpoints": [], "scenarios": [], "data_entities": [], "depends_on": []}


def requirement_id(ears_pattern: str, trigger: str, target: str) -> str:
    """`REQ-<hash>` (ADR-0009 point 1, ADR-0015's `sha1(...)[:10]`
    algorithm) - deterministic across runs regardless of discovery order,
    unlike a sequential counter.

    Public (not `_`-prefixed): `generators/gherkin.py` reuses this exact
    function to recompute the same id for `@REQ-<hash>` tags, rather than
    re-deriving the hash's input format independently and risking drift
    (ADR-0013 point 3).
    Details: docs/dev/generators/requirements.md#requirement_id
    """
    return f"REQ-{short_hash(f'{ears_pattern}|{trigger}|{target}')}"


def _screen_id(page_url: str) -> str:
    return f"SCR-{short_hash(page_url)}"


@dataclass(frozen=True)
class _RequirementFacts:
    """What one extraction rule knows about one requirement, before
    `_requirement` turns it into `requirements.json`'s own shape - kept
    as one object rather than threaded through as individual arguments,
    the same "four-plus arguments become a dataclass" rule every other
    multi-fact assembly in this codebase follows.
    Details: docs/dev/generators/requirements.md#_requirementfacts
    """

    ears_pattern: str
    syntax_text: str
    trigger: str
    target: str
    confidence: str
    links: Dict[str, List[str]]
    open_questions: Tuple[str, ...] = ()


def _requirement(facts: _RequirementFacts, run_id: str) -> Dict[str, Any]:
    return {
        "id": requirement_id(facts.ears_pattern, facts.trigger, facts.target),
        "ears_pattern": facts.ears_pattern,
        "syntax_text": facts.syntax_text,
        "confidence": facts.confidence,
        # Reserved: pragma has no stable per-interaction/HAR/screenshot id
        # scheme yet (the same gap catalog.json's own x-observed-variants
        # left reserved, ticket #101).
        "derived_from": [],
        "links": facts.links,
        "coverage_ref": {"run_id": run_id},
        "hitl_status": "unreviewed",
        "open_questions": list(facts.open_questions),
    }


def _event_driven_requirements(inferred_requests: Sequence[Any], run_id: str) -> List[Dict[str, Any]]:
    """WHEN a component is interacted with, THE SYSTEM SHALL call the
    endpoint it triggered - one requirement per distinct trigger.
    Details: docs/dev/generators/requirements.md#_event_driven_requirements
    """
    requirements = []
    for request in inferred_requests:
        target = f"{request.method} {request.endpoint}"
        for page_url, path in request.triggered_by:
            trigger = f"the user interacts with {path} on {page_url}"
            facts = _RequirementFacts(
                ears_pattern="event_driven",
                syntax_text=f"WHEN the user interacts with {path} on {page_url}, THE SYSTEM SHALL call {target}",
                trigger=trigger, target=target, confidence="observed",
                links={**_NO_LINKS, "screens": [_screen_id(page_url)], "endpoints": [target]},
            )
            requirements.append(_requirement(facts, run_id))
    return requirements


def _ubiquitous_requirements(inferred_requests: Sequence[Any], run_id: str) -> List[Dict[str, Any]]:
    """THE SYSTEM SHALL retrieve data automatically when a screen is
    displayed - one requirement per page whose own load fired the call,
    with no component involved.
    Details: docs/dev/generators/requirements.md#_ubiquitous_requirements
    """
    requirements = []
    for request in inferred_requests:
        target = f"{request.method} {request.endpoint}"
        for page_url in request.loaded_by:
            facts = _RequirementFacts(
                ears_pattern="ubiquitous",
                syntax_text=f"THE SYSTEM SHALL call {target} when {page_url} is displayed",
                trigger=f"{page_url} is displayed", target=target, confidence="observed",
                links={**_NO_LINKS, "screens": [_screen_id(page_url)], "endpoints": [target]},
            )
            requirements.append(_requirement(facts, run_id))
    return requirements


def _unwanted_behavior_requirements(inferred_requests: Sequence[Any], run_id: str) -> List[Dict[str, Any]]:
    """IF a call fails, THEN THE SYSTEM SHALL answer with the observed
    failure status - the crawl only ever captures the response's own
    status code, never the resulting UI, hence the open question every
    one of these carries.
    Details: docs/dev/generators/requirements.md#_unwanted_behavior_requirements
    """
    requirements = []
    for request in inferred_requests:
        failures = tuple(code for code in request.status_codes if code >= 400)
        if not failures:
            continue
        target = f"{request.method} {request.endpoint}"
        facts = _RequirementFacts(
            ears_pattern="unwanted_behavior",
            syntax_text=f"IF the call to {target} fails, THEN THE SYSTEM SHALL respond with {failures[0]}",
            trigger=f"the call to {target} fails", target=target, confidence="observed",
            links={**_NO_LINKS, "endpoints": [target]},
            open_questions=(
                f"The crawl observed a {failures[0]} response from {target} but not the resulting UI state - "
                "what does the interface show when this fails?",
            ),
        )
        requirements.append(_requirement(facts, run_id))
    return requirements


def _optional_feature_requirements(data_model_document: Dict[str, Any], run_id: str) -> List[Dict[str, Any]]:
    """WHERE a declared-optional field is provided, THE SYSTEM SHALL
    accept it - `nullable` fields only, from `data-model.json`'s own
    entities. A UI heuristic (the markup declares it optional; nothing
    here observed the field actually being omitted), so `"inferred"`,
    not `"observed"`.
    Details: docs/dev/generators/requirements.md#_optional_feature_requirements
    """
    requirements = []
    for entity_name, entity in data_model_document["entities"].items():
        for field_name, field in entity["fields"].items():
            if not field["nullable"]:
                continue
            facts = _RequirementFacts(
                ears_pattern="optional_feature",
                syntax_text=f"WHERE the user provides {field_name}, THE SYSTEM SHALL accept it as part of {entity_name}",
                trigger=f"the user provides {field_name} for {entity_name}", target=entity_name,
                confidence="inferred", links={**_NO_LINKS, "data_entities": [entity_name]},
            )
            requirements.append(_requirement(facts, run_id))
    return requirements


def _rule_based_requirements(
    rules: Sequence[Any],
    rule_field_entities: Dict[Tuple[str, str, str], Tuple[str, str]],
    run_id: str,
) -> List[Dict[str, Any]]:
    """THE SYSTEM SHALL enforce a declared markup constraint - one
    requirement per `SemanticRule` whose `GOVERNS` edge resolved to a
    real `Field`/`Entity`. `record_rules`'s `GOVERNS` is best-effort (its
    own docstring); a Rule with no resolved Field simply isn't in
    `rule_field_entities` and is silently skipped here, the same stance
    the writer itself takes rather than erroring.

    Only `kind="declared"` rows are ever turned into a requirement -
    `kind="inferred"` (cross-field logic, human-reviewed) is out of
    scope per #190/#193 and must never be implied as covered here, even
    though nothing in this codebase produces one yet.
    Details: docs/dev/generators/requirements.md#_rule_based_requirements
    """
    requirements = []
    for rule in rules:
        if rule.kind != "declared":
            continue
        page_url, path = rule.derived_from
        resolved = rule_field_entities.get((page_url, path, rule.statement))
        if resolved is None:
            continue
        field_name, entity_name = resolved
        facts = _RequirementFacts(
            ears_pattern="ubiquitous",
            syntax_text=f"THE SYSTEM SHALL enforce {rule.statement} on {field_name}",
            trigger=f"{rule.statement} on {field_name}", target=entity_name,
            confidence="inferred",
            links={**_NO_LINKS, "screens": [_screen_id(page_url)], "data_entities": [entity_name]},
        )
        requirements.append(_requirement(facts, run_id))
    return requirements


def _rule_field_entities_by_key(rows: Sequence[Dict[str, str]]) -> Dict[Tuple[str, str, str], Tuple[str, str]]:
    """`{(page_url, path, statement): (field, entity)}` from
    `LadybugGraphStore.get_rule_field_entities()`'s row shape - the
    lookup key `_rule_based_requirements` needs to match a `SemanticRule`
    (identified by its own `derived_from` plus `statement`) back to the
    `Field`/`Entity` its `GOVERNS` edge resolved to.
    Details: docs/dev/generators/requirements.md#_rule_field_entities_by_key
    """
    return {(row["page_url"], row["path"], row["statement"]): (row["field"], row["entity"]) for row in rows}


def build_requirements_document(request: DocumentRequest) -> Dict[str, Any]:
    """The full `requirements.json` payload: every EARS pattern this
    crawl has real support for, deduplicated by `id` (the same
    deterministic hash collapses a genuinely repeated observation into
    one requirement rather than one per occurrence).
    Details: docs/dev/generators/requirements.md#build_requirements_document
    """
    run_id = request.settings.get("run_id", "")
    inferred_requests = request.graph_store.get_inferred_requests()
    data_model_document = build_data_model_document(request)
    rules = request.graph_store.get_rules()
    rule_field_entities = _rule_field_entities_by_key(request.graph_store.get_rule_field_entities())

    requirements: Dict[str, Dict[str, Any]] = {}
    for requirement in (
        _event_driven_requirements(inferred_requests, run_id)
        + _ubiquitous_requirements(inferred_requests, run_id)
        + _unwanted_behavior_requirements(inferred_requests, run_id)
        + _optional_feature_requirements(data_model_document, run_id)
        + _rule_based_requirements(rules, rule_field_entities, run_id)
    ):
        requirements[requirement["id"]] = requirement

    return {"requirements": [requirements[key] for key in sorted(requirements)]}


def _screen_module_labels(request: DocumentRequest) -> Dict[str, str]:
    """`{SCR-<hash>: module_label}` for every screen with a derived
    module - `prd.md`'s own grouping (ADR-0009 point 4), computed the
    same hybrid path-prefix/Leiden pass `architecture.calm.json` uses
    (docs/adr/0007), not a second, differently-derived module structure.

    `core.graph_metrics.build_screen_graph` (not
    `generators/graph_export.py::build_export_graph`) supplies the
    minimal `Pantalla`-only input - avoids a circular import, since
    `graph_export.py` itself imports this module's
    `build_requirements_document` for `Requisito` population
    (ADR-0009 point 5).
    Details: docs/dev/generators/requirements.md#_screen_module_labels
    """
    store = request.graph_store
    root = route_shape(request.settings.get("target", "")) or None
    metrics = compute_graph_metrics(build_screen_graph(store, store.get_edges()), root=root)
    return {_screen_id(module.node_id): module.module_label or module.module_id for module in metrics.node_modules}


def _requirement_row(requirement: Dict[str, Any]) -> str:
    open_questions = f" ({len(requirement['open_questions'])} open question(s))" if requirement["open_questions"] else ""
    return (
        f"| `{requirement['id']}` | {requirement['ears_pattern']} | {requirement['syntax_text']} "
        f"| {requirement['confidence']} | {requirement['hitl_status']}{open_questions} |"
    )


def _render_prd_view(document: Dict[str, Any], module_labels: Dict[str, str], site: str) -> str:
    """`prd.md` - mechanically rendered from `requirements.json`, grouped
    by architectural module (ADR-0007) and HITL review status
    (ADR-0009 point 4), never hand-authored in parallel with it.
    Details: docs/dev/generators/requirements.md#_render_prd_view
    """
    lines = [f"# Requirements: {site}", ""]
    requirements = document["requirements"]
    if not requirements:
        lines.append("No requirements were extracted from this crawl - no observed traffic to derive them from.")
        return "\n".join(lines) + "\n"

    lines += [
        f"{len(requirements)} requirement(s) in EARS syntax, extracted from observed traffic and "
        "declared markup - never narrated. Every one starts `unreviewed`; this document is the "
        "input to a human review pass, not a substitute for one.",
        "",
    ]

    by_module: Dict[str, List[Dict[str, Any]]] = {}
    unmapped: List[Dict[str, Any]] = []
    for requirement in requirements:
        screens = requirement["links"]["screens"]
        if not screens:
            unmapped.append(requirement)
            continue
        for screen_id in screens:
            label = module_labels.get(screen_id, screen_id)
            by_module.setdefault(label, []).append(requirement)

    for label, group in sorted(by_module.items()):
        lines += [f"## {label}", "", "| ID | Pattern | Requirement | Confidence | Status |", "|---|---|---|---|---|"]
        lines += [_requirement_row(requirement) for requirement in group]
        lines.append("")

    if unmapped:
        lines += [
            "## Not tied to a screen", "",
            "| ID | Pattern | Requirement | Confidence | Status |", "|---|---|---|---|---|",
        ]
        lines += [_requirement_row(requirement) for requirement in unmapped]
        lines.append("")

    return "\n".join(lines)


def _as_json(document: Dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("prd")
class RequirementsDocument(DocumentGenerator):
    """`requirements.json` (source, schema-validated) and `prd.md` (view,
    grouped by module and review status) - docs/adr/0009.
    Details: docs/dev/generators/requirements.md#requirementsdocument
    """

    name = "prd"
    title = "Requirements"
    purpose = "Requirements in EARS syntax, extracted from observed traffic and declared markup, grouped by module."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        document = build_requirements_document(request)
        validate_against_schema(document, _SCHEMA_PATH)
        source = _as_json(document)
        view = _render_prd_view(document, _screen_module_labels(request), request.site)
        return (
            DocumentOutput(filename="requirements", kind="source", extension="json", content=source),
            DocumentOutput(filename="prd", kind="view", extension="md", content=view),
        )
