"""`change-log.json` - a cross-run diff over every entity kind that
already carries a Short hash ID, docs/adr/0019.

**Per-entity, scoped to Short-hash IDs, and only those.** `interaction:`/
`har:` citations from `evidence-log` are excluded on purpose (ADR-0017
already established their Kùzu `SERIAL` ids aren't stable across
re-crawls - diffing them would compare noise, not signal). Every kind
diffed here already has a deterministic id: `SCR-` (screens), `REQ-`
(requirements), `EP-` (endpoints), `MOD-` (modules), `CH-`/`MSG-`
(channels/messages - always an empty snapshot today, since
`AsyncAPIDocument.generate` has no real detection instrumentation to
read from yet, ADR-0018).

**The three-way split is forced by how the IDs are built, not a free
design choice** (ADR-0019 point 2). Every Short hash is derived from an
entity's own identity-defining fields, so an entity whose identity
changes doesn't keep its id - it becomes a different one, surfacing as a
`no_longer_observed`/`newly_discovered` pair rather than a `changed`
entry. `diff_entities` needs no special-casing for this: it is a pure
function of two `{id: fields}` maps, and the identity-vs-field-change
behavior falls out of using the id as the map key, not from any logic
this module writes.

**Snapshots come from each document's own real build function**
(`build_export_graph`, matching this map's established "call the
function, don't read the file" discipline) for the *current* run.
There is no equivalent live read for a *previous* run - a re-crawl's
graph store has already moved on - so `previous_snapshot` arrives via
`DocumentRequest.settings` instead, supplied by whichever future caller
wires it up from `runs.json`'s own per-run history
(`utils/io.py::record_run_manifest`). Until a caller does,
`change-log.json` still generates: an honest empty diff, `run_id_from`
absent, rather than either refusing to produce anything or - worse -
reading every current entity as spuriously "newly discovered" against a
previous run this module never actually saw.

Details: docs/dev/generators/change_log.md#module
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from utils.short_hash import short_hash
from .graph_export import build_export_graph

_SCHEMA_PATH = "schemas/change-log.schema.json"

_KINDS: Tuple[str, ...] = ("screens", "requirements", "endpoints", "modules", "channels", "messages")


@dataclass(frozen=True)
class EntityChange:
    """One entity whose id held steady across both runs but at least one
    other field moved.
    Details: docs/dev/generators/change_log.md#entitychange
    """

    id: str
    changed_fields: Tuple[str, ...]
    before: Dict[str, Any]
    after: Dict[str, Any]


@dataclass(frozen=True)
class EntityDiff:
    """One entity kind's three-way split (ADR-0019 point 2).
    Details: docs/dev/generators/change_log.md#entitydiff
    """

    newly_discovered: Tuple[str, ...]
    no_longer_observed: Tuple[str, ...]
    changed: Tuple[EntityChange, ...]


def diff_entities(previous: Dict[str, Dict[str, Any]], current: Dict[str, Dict[str, Any]]) -> EntityDiff:
    """The one diff algorithm every entity kind uses - a pure function of
    two `{id: fields}` maps. An id present in `current` but not
    `previous` is `newly_discovered`; present in `previous` but not
    `current` is `no_longer_observed`; present in both only becomes
    `changed` when some field besides `id` itself actually differs -
    added, removed, or changed value all count.
    Details: docs/dev/generators/change_log.md#diff_entities
    """
    previous_ids, current_ids = set(previous), set(current)
    changed = []
    for entity_id in sorted(previous_ids & current_ids):
        before, after = previous[entity_id], current[entity_id]
        field_names = (set(before) | set(after)) - {"id"}
        changed_fields = tuple(sorted(name for name in field_names if before.get(name) != after.get(name)))
        if changed_fields:
            changed.append(EntityChange(id=entity_id, changed_fields=changed_fields, before=before, after=after))

    return EntityDiff(
        newly_discovered=tuple(sorted(current_ids - previous_ids)),
        no_longer_observed=tuple(sorted(previous_ids - current_ids)),
        changed=tuple(changed),
    )


def _screen_id(page_url: str) -> str:
    return f"SCR-{short_hash(page_url)}"


def _endpoint_id(target: str) -> str:
    return f"EP-{short_hash(target)}"


def _snapshots_from_export_graph(graph_nodes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """`screens`/`requirements`/`endpoints`/`modules` snapshots, all from
    one `build_export_graph` call - `Requisito`/`Modulo` nodes already
    carry their real `REQ-<hash>`/`MOD-<slug|hash>` id as `node["id"]`
    (`generators/graph_export.py::_requisito_nodes`/`_modulo_nodes`);
    `Pantalla`/`Endpoint` nodes don't (`node["id"]` is the raw page url /
    `"{method} {endpoint}"` string), so `SCR-`/`EP-` are minted here from
    that raw id, the same formula `_requisito_nodes` itself already uses
    to resolve a `Pantalla`'s `SCR-<hash>` for its own `implementa` edges.
    Details: docs/dev/generators/change_log.md#_snapshots_from_export_graph
    """
    screens: Dict[str, Dict[str, Any]] = {}
    endpoints: Dict[str, Dict[str, Any]] = {}
    requirements: Dict[str, Dict[str, Any]] = {}
    modules: Dict[str, Dict[str, Any]] = {}
    for node in graph_nodes:
        fields = {key: value for key, value in node.items() if key != "id"}
        if node["type"] == "Pantalla":
            screens[_screen_id(node["id"])] = fields
        elif node["type"] == "Endpoint":
            endpoints[_endpoint_id(node["id"])] = fields
        elif node["type"] == "Requisito":
            requirements[node["id"]] = fields
        elif node["type"] == "Modulo":
            modules[node["id"]] = fields
    return {"screens": screens, "requirements": requirements, "endpoints": endpoints, "modules": modules}


def _current_snapshots(request: DocumentRequest) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Every kind's current-run snapshot. `channels`/`messages` stay
    empty - `AsyncAPIDocument.generate` has no real detection
    instrumentation to read from yet (ADR-0018) - present in the shape
    for the same forward-looking reason `asyncapi.json`'s own id scheme
    was built ahead of real data (ticket #111).
    Details: docs/dev/generators/change_log.md#_current_snapshots
    """
    snapshots = _snapshots_from_export_graph(build_export_graph(request)["@graph"])
    snapshots["channels"] = {}
    snapshots["messages"] = {}
    return snapshots


def _diff_shape(diff: EntityDiff) -> Dict[str, Any]:
    return {
        "newly_discovered": list(diff.newly_discovered),
        "no_longer_observed": list(diff.no_longer_observed),
        "changed": [
            {"id": change.id, "changed_fields": list(change.changed_fields)}
            for change in diff.changed
        ],
    }


def build_change_log_document(request: DocumentRequest) -> Dict[str, Any]:
    """`change-log.json` - `run_id_from`/`run_id_to` plus each kind's own
    three-way split. `run_id_from`/every kind's diff is honestly empty
    when `request.settings["previous_snapshot"]` is absent: no caller has
    wired a previous run's data in yet, and treating "nothing to compare
    against" as "everything is newly discovered" would be inventing a
    diff this run never actually observed.
    Details: docs/dev/generators/change_log.md#build_change_log_document
    """
    current = _current_snapshots(request)
    previous = request.settings.get("previous_snapshot")

    document: Dict[str, Any] = {
        "run_id_from": request.settings.get("previous_run_id"),
        "run_id_to": request.settings.get("run_id", ""),
        "kinds": {},
    }
    for kind in _KINDS:
        if previous is None:
            diff = EntityDiff(newly_discovered=(), no_longer_observed=(), changed=())
        else:
            diff = diff_entities(previous.get(kind, {}), current[kind])
        document["kinds"][kind] = _diff_shape(diff)
    return document


def _kind_lines(kind: str, diff: Dict[str, Any]) -> List[str]:
    if not diff["newly_discovered"] and not diff["no_longer_observed"] and not diff["changed"]:
        return []
    lines = [f"## {kind.replace('_', ' ').title()}", ""]
    if diff["newly_discovered"]:
        lines += ["**Newly discovered:**", ""] + [f"- `{entity_id}`" for entity_id in diff["newly_discovered"]] + [""]
    if diff["no_longer_observed"]:
        lines += ["**No longer observed:**", ""] + [f"- `{entity_id}`" for entity_id in diff["no_longer_observed"]] + [""]
    if diff["changed"]:
        lines += ["**Changed:**", ""]
        lines += [f"- `{c['id']}`: {', '.join(c['changed_fields'])}" for c in diff["changed"]]
        lines.append("")
    return lines


def _render_change_log_view(document: Dict[str, Any], site: str) -> str:
    """`change-log.md` - mechanically rendered from `change-log.json`,
    never hand-authored in parallel with it.
    Details: docs/dev/generators/change_log.md#_render_change_log_view
    """
    lines = [f"# Change Log: {site}", ""]
    if document["run_id_from"] is None:
        lines += [
            "No previous run was available to compare against - this run has nothing to diff yet. "
            "A future run, once a prior run's data is supplied, will show what changed between them.",
            "",
        ]
        return "\n".join(lines) + "\n"

    lines.append(f"Comparing `{document['run_id_from']}` -> `{document['run_id_to']}`.")
    lines.append("")
    any_changes = False
    for kind in _KINDS:
        kind_lines = _kind_lines(kind, document["kinds"][kind])
        if kind_lines:
            any_changes = True
        lines += kind_lines
    if not any_changes:
        lines.append("No changes between these two runs.")
        lines.append("")
    return "\n".join(lines)


def _as_json(document: Dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("change-log")
class ChangeLogDocument(DocumentGenerator):
    """`change-log.json` (source, schema-validated) and `change-log.md`
    (view) - docs/adr/0019.
    Details: docs/dev/generators/change_log.md#changelogdocument
    """

    name = "change-log"
    title = "Change Log"
    purpose = "Per-entity diff between this run and the previous one, scoped to every Short-hash-ID'd entity kind."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        document = build_change_log_document(request)
        validate_against_schema(document, _SCHEMA_PATH)
        view = _render_change_log_view(document, request.site)
        return (
            DocumentOutput(filename="change-log", kind="source", extension="json", content=_as_json(document)),
            DocumentOutput(filename="change-log", kind="view", extension="md", content=view),
        )
