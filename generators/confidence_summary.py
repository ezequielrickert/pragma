"""`confidence-summary.json` - derived confidence rollups across four
source documents, citing each by reference, docs/adr/0029.

**Derived rollups only, never re-emitted values** (point 1). Each
`sources` entry is a percentage/count/distribution over its source
document's own confidence-shaped field, citing that document by its
`DocumentOutput.filename` - never restating an individual requirement's
`confidence`, a field's numeric score, or a finding's `level`. Re-
emitting those would be the exact duplicate-view anti-pattern this
whole map exists to eliminate, one document away from where the rest of
it landed.

**What "confidence" means per source, since only `prd` calls it that.**
`prd`'s own `confidence` field (`observed`/`inferred`/`assumed`,
ADR-0009) is the literal, unambiguous case. `data-model.json`'s own
per-field `confidence` is a numeric 0-1 score (ADR-0008) - rolled up as
count/mean/min/max rather than forced into `prd`'s three-category
vocabulary, which was never built to describe a continuous score.
`usability`/`accessibility` carry no field literally named `confidence`
at all; their EARL `level` (ADR-0011/0012) is the one dimension that
varies per finding and speaks to how much scrutiny it deserves - rolled
up the same way `prd`'s categories are, by count per level.

**Feeds `dashboard`'s tile, doesn't recompute inline** (point 2).
`dashboard`'s ADR-0016 landing-page tile ("requirement confidence
split") is `sources.prd` read directly - this document exists so that
computation happens in exactly one place.

**Per-run snapshot, not a cross-run tracker** (point 3). Cross-run
confidence *trends* are `change-log`'s job (ADR-0019 already names a
requirement's `confidence` upgrading as its own worked example); this
document captures only the current run's distribution.

Details: docs/dev/generators/confidence_summary.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from .accessibility_act import build_earl_document as build_accessibility_earl_document
from .data_model import build_data_model_document
from .requirements import build_requirements_document
from .usability_act import build_earl_document as build_usability_earl_document

_SCHEMA_PATH = "schemas/confidence-summary.schema.json"

_CONFIDENCE_CATEGORIES: Tuple[str, ...] = ("observed", "inferred", "assumed")
_EARL_LEVELS: Tuple[str, ...] = ("error", "warning", "note", "none")


def _prd_rollup(request: DocumentRequest) -> Dict[str, Any]:
    """`prd`'s own confidence categories (ADR-0009), by count.
    Details: docs/dev/generators/confidence_summary.md#_prd_rollup
    """
    document = build_requirements_document(request)
    by_confidence = {category: 0 for category in _CONFIDENCE_CATEGORIES}
    for requirement in document["requirements"]:
        by_confidence[requirement["confidence"]] += 1
    return {"source_document": "requirements", "by_confidence": by_confidence, "total": len(document["requirements"])}


def _data_model_rollup(request: DocumentRequest) -> Dict[str, Any]:
    """`data-model.json`'s numeric per-field confidence, as descriptive
    statistics rather than forced into `prd`'s three categories.
    Details: docs/dev/generators/confidence_summary.md#_data_model_rollup
    """
    document = build_data_model_document(request)
    values: List[float] = [
        field["confidence"] for entity in document["entities"].values() for field in entity["fields"].values()
    ]
    if not values:
        return {"source_document": "data-model", "count": 0, "mean_confidence": None, "min_confidence": None, "max_confidence": None}
    return {
        "source_document": "data-model", "count": len(values),
        "mean_confidence": round(sum(values) / len(values), 2),
        "min_confidence": min(values), "max_confidence": max(values),
    }


def _level_rollup(source_document: str, earl_document: Dict[str, Any]) -> Dict[str, Any]:
    """One EARL document's `level` distribution, by count - the one
    per-finding dimension `usability`/`accessibility` actually vary.
    Details: docs/dev/generators/confidence_summary.md#_level_rollup
    """
    by_level = {level: 0 for level in _EARL_LEVELS}
    for assertion in earl_document["@graph"]:
        by_level[assertion["level"]] += 1
    return {"source_document": source_document, "by_level": by_level, "total": len(earl_document["@graph"])}


def build_confidence_summary(request: DocumentRequest) -> Dict[str, Any]:
    """The full `confidence-summary.json` payload - one rollup per
    source, each computed by calling that document's own real build
    function directly, never re-deriving or re-reading a file.
    Details: docs/dev/generators/confidence_summary.md#build_confidence_summary
    """
    return {
        "run_id": request.settings.get("run_id", ""),
        "sources": {
            "prd": _prd_rollup(request),
            "data-model": _data_model_rollup(request),
            "usability": _level_rollup("usability.earl", build_usability_earl_document(request)),
            "accessibility": _level_rollup("accessibility.earl", build_accessibility_earl_document(request)),
        },
    }


def _render_confidence_summary_view(summary: Dict[str, Any]) -> str:
    """`confidence-summary.md` - mechanically rendered from
    `confidence-summary.json`, never hand-authored in parallel with it.
    Details: docs/dev/generators/confidence_summary.md#_render_confidence_summary_view
    """
    lines = ["# Confidence Summary", "", "| Source | Breakdown | Total |", "|---|---|---|"]
    prd = summary["sources"]["prd"]
    lines.append(
        f"| {prd['source_document']} | "
        f"{', '.join(f'{category} {count}' for category, count in prd['by_confidence'].items())} | {prd['total']} |"
    )
    data_model = summary["sources"]["data-model"]
    lines.append(
        f"| {data_model['source_document']} | mean {data_model['mean_confidence']}, "
        f"range [{data_model['min_confidence']}, {data_model['max_confidence']}] | {data_model['count']} |"
    )
    for key in ("usability", "accessibility"):
        rollup = summary["sources"][key]
        lines.append(
            f"| {rollup['source_document']} | "
            f"{', '.join(f'{level} {count}' for level, count in rollup['by_level'].items())} | {rollup['total']} |"
        )
    lines.append("")
    return "\n".join(lines)


def _as_json(summary: Dict[str, Any]) -> str:
    return json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@DOCUMENT_REGISTRY.register("confidence-summary")
class ConfidenceSummaryDocument(DocumentGenerator):
    """`confidence-summary.json` (source, schema-validated) and
    `confidence-summary.md` (view) - docs/adr/0029.
    Details: docs/dev/generators/confidence_summary.md#confidencesummarydocument
    """

    name = "confidence-summary"
    title = "Confidence Summary"
    purpose = "Derived confidence rollups across requirements, data-model, usability, and accessibility - citing each source by reference."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        summary = build_confidence_summary(request)
        validate_against_schema(summary, _SCHEMA_PATH)
        view = _render_confidence_summary_view(summary)
        return (
            DocumentOutput(filename="confidence-summary", kind="source", extension="json", content=_as_json(summary)),
            DocumentOutput(filename="confidence-summary", kind="view", extension="md", content=view),
        )
