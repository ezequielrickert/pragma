"""`evidence-log.jsonl` - a per-run index of `interaction:<id>`/`har:<id>`
evidence citations, docs/adr/0017.

**Indexes only what has no other resolution path.** `interaction:<id>`
and `har:<id>` exist solely as graph nodes (`Interaction`/`Request`,
`database/ladybug/schema.py`) with no portable file representation - a
reader outside the pipeline, or without graph access, has no way to
resolve one otherwise. AXTree/DOM snapshots are deliberately **not**
re-indexed here: `tree` already made those resolvable via `SCR-<hash>`
plus a per-leaf `x-axtree-ref` JSON Pointer (ADR-0003), and duplicating
that would be the exact duplicate-view anti-pattern this map exists to
eliminate. `screenshot:<id>` is a **reserved** kind - present in the
schema's `kind` enum, never actually emitted, since no screenshot-capture
instrumentation exists in this crawl (the same reserved-field precedent
`coverage.json` set, ADR-0001).

**Per-run, not cross-run.** `Interaction`/`Request` both use Kùzu's
`SERIAL PRIMARY KEY`, an auto-increment counter local to one database
instance - `interaction:42` from one crawl and `interaction:42` from a
re-crawl are not the same interaction. Each row carries its own `run_id`
rather than this being a cross-run accumulating file, which would need a
compound `(run_id, local_id)` key to avoid silent collisions a per-run
file gets for free.

**A lightweight index, not a duplicate.** Each row is `id` (the exact
citation string in use elsewhere), `kind`, `run_id`, and one short
human-readable `summary` - never a copy of the graph node's full field
set. The graph stays the authoritative full-detail source, queried
directly, the same division of labor `export.json` already has with it
(ADR-0002).

Details: docs/dev/generators/evidence_log.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.jsonl import as_jsonl
from utils.schema_validation import validate_against_schema

_SCHEMA_PATH = "schemas/evidence-log.schema.json"


def _interaction_summary(evidence: Dict[str, Any]) -> str:
    action, value = evidence["action"], evidence["value"]
    control = f"{action} {value!r}" if value else action
    return f"{control} on {evidence['path']} ({evidence['page_url']})"


def _interaction_row(evidence: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    return {
        "id": f"interaction:{evidence['id']}", "kind": "interaction",
        "run_id": run_id, "summary": _interaction_summary(evidence),
    }


def _request_summary(evidence: Dict[str, Any]) -> str:
    target = f"{evidence['host']}{evidence['path_pattern']}" if evidence["host"] else evidence["path"]
    status = evidence["status"]
    return f"{evidence['method']} {target} -> {status}" if status is not None else f"{evidence['method']} {target}"


def _request_row(evidence: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    return {
        "id": f"har:{evidence['id']}", "kind": "har",
        "run_id": run_id, "summary": _request_summary(evidence),
    }


def build_evidence_log(request: DocumentRequest) -> List[Dict[str, Any]]:
    """Every real `interaction:<id>`/`har:<id>` this run's graph can back,
    in id order within each kind - `interaction:` rows first, `har:` rows
    after, never interleaved, so a reader scanning the file finds one
    kind's ids monotonic.
    Details: docs/dev/generators/evidence_log.md#build_evidence_log
    """
    run_id = request.settings.get("run_id", "")
    store = request.graph_store
    rows = [_interaction_row(evidence, run_id) for evidence in store.get_interaction_evidence()]
    rows += [_request_row(evidence, run_id) for evidence in store.get_request_evidence()]
    return rows


@DOCUMENT_REGISTRY.register("evidence-log")
class EvidenceLogDocument(DocumentGenerator):
    """Details: docs/dev/generators/evidence_log.md#evidencelogdocument"""

    name = "evidence-log"
    title = "Evidence Log"
    purpose = "Per-run index of interaction:<id>/har:<id> evidence citations, resolving another document's derived_from pointers."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        # A bare `str` return always auto-wraps to `kind="view"`
        # (`core.documents.DocumentGenerator.outputs`) - this is a source
        # document (CONTEXT.md's taxonomy: machine-checkable ground
        # truth an evidence citation resolves against), so it declares
        # its own `DocumentOutput` explicitly, the same way
        # `graph_export.py`'s single-file `export.json` does.
        rows = build_evidence_log(request)
        validate_against_schema(rows, _SCHEMA_PATH)
        return (DocumentOutput(filename="evidence-log", kind="source", extension="jsonl", content=as_jsonl(rows)),)
