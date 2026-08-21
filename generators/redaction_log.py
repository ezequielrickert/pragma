"""`redaction-log.jsonl` - a per-run index of every redaction event a
document's own redaction mechanism actually applied, docs/adr/0021.

**Consolidation, not a universal mechanism** (ADR-0021 point 1). This
module never redacts anything itself; it indexes redaction events *after
the fact* from whichever documents already redact by their own
document-appropriate mechanism. `openapi`'s OpenAPI Overlay workflow
(ADR-0004) is the only real source in v1 - the Overlay Specification is
conformance-scoped to OpenAPI documents, so it can't be mandated as a
universal mechanism for CALM, EARL, SARIF, or `tokens.json`; a future
document picks its own redaction shape when it needs one, and gets
indexed here the same way once it does.

**Only the Overlay layer, not capture-time redaction.** `openapi.raw.yaml`
already reflects the *first* redaction pass (`spiders/content/redaction.py`
- secret-named fields dropped, emails/card-like numbers/tokens scrubbed at
capture time) before this module ever sees it; that pass has no structured
target/action record the way an Overlay action does, so which field it
touched isn't something this log can honestly cite. What this log indexes
is the *second* pass: the hand-authored `redaction.overlay.yaml` rules
applied on top.

**One row per concrete field, not per rule.** `generators/openapi_overlay.py`
resolves each action's target (including any `[*]` wildcard) against the
pre-redaction document, so a wildcard rule that touches five fields is
five rows, each citing its own concrete `field_path` - a rule that never
matches this run is not evidence anything was redacted, and contributes no
row (ADR-0021 point 2). `reason` is the action's own `description` field
(the real Overlay Specification's optional field, a maintainer's own
stated legal/business reason) - empty, not invented, when the action
carries none.

**Never the value, by construction** (ADR-0021 point 3): `evidence` cites
the raw-private and public artifact filenames (both existing is the proof
redaction happened), never the field's own redacted content. Every field
here describes metadata about a redaction, so the document is safe to read
freely without itself needing to be hidden.

Details: docs/dev/generators/redaction_log.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.jsonl import as_jsonl
from utils.schema_validation import validate_against_schema
from .openapi import PUBLIC_FILENAME, RAW_FILENAME, build_openapi_document, load_overlay
from .openapi_overlay import redaction_events

_SCHEMA_PATH = "schemas/redaction-log.schema.json"


def _redaction_row(field_path: str, action: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    return {
        "source_document": "openapi",
        "field_path": field_path,
        "reason": action.get("description", ""),
        "run_id": run_id,
        "evidence": {"raw_artifact": RAW_FILENAME, "public_artifact": PUBLIC_FILENAME},
    }


def build_redaction_log(request: DocumentRequest) -> List[Dict[str, Any]]:
    """Every field `openapi`'s Overlay workflow actually redacted this run,
    one row per concrete match. Recomputes `openapi.raw.yaml`'s own
    document from the graph directly (deterministic, no model call) rather
    than reading a file `openapi`'s own generator may not have written
    this run - the same "call the real build function" discipline every
    cross-generator call in this map already follows.
    Details: docs/dev/generators/redaction_log.md#build_redaction_log
    """
    inferred_requests = request.graph_store.get_inferred_requests()
    raw_document = build_openapi_document(inferred_requests, request.site)
    overlay = load_overlay()
    run_id = request.settings.get("run_id", "")
    return [
        _redaction_row(field_path, action, run_id)
        for field_path, action in redaction_events(raw_document, overlay)
    ]


@DOCUMENT_REGISTRY.register("redaction-log")
class RedactionLogDocument(DocumentGenerator):
    """`redaction-log.jsonl` (source, schema-validated), no view - an
    audit trail read as rows, not prose, the same shape `evidence-log`
    already settled on for a per-run index file.
    Details: docs/dev/generators/redaction_log.md#redactionlogdocument
    """

    name = "redaction-log"
    title = "Redaction Log"
    purpose = "Per-run index of every field openapi's redaction overlay actually redacted, and why - never the value it removed."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        rows = build_redaction_log(request)
        validate_against_schema(rows, _SCHEMA_PATH)
        return (DocumentOutput(filename="redaction-log", kind="source", extension="jsonl", content=as_jsonl(rows)),)
