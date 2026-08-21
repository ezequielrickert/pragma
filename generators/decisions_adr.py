"""`decisions.adr/` - one MADR-format decision record per `requirements.json`
entry pragma classified `inferred`/`assumed`, docs/adr/0023.

**Trigger: `inferred`/`assumed`, never `observed`** (ADR-0023 point 1).
`prd`'s own confidence vocabulary (ADR-0009) already draws exactly this
line: `observed` means directly verified from crawl traffic, with no
judgment call to explain. A rebuild team reads a decision record to
understand or challenge a classification pragma inferred rather than
witnessed - an `observed` requirement has nothing here to explain.

**MADR's own sequential numbering, not this map's Short hash family**
(ADR-0023 point 2). Each entry is a real file,
`decisions.adr/0001-<slug>.md`, numbered the same way this repo's own
`docs/adr/` already is - MADR's native identity mechanism. The entity
the decision is about (`REQ-<hash>`) is cited in the body as a
cross-reference, never folded into the filename itself: these are
pragma's own crawl-time judgment calls, a different kind of thing than
the stable observed-entity identity a Short hash ID names.

**A minimal MADR subset, not the full template.** MADR's own
"Considered Options"/"Decision Drivers" sections describe a real
deliberation between named alternatives - this document has none to
report honestly: pragma's classification rules are single-path
heuristics (a field is either declared nullable or it isn't), not a
choice among options a human weighed. Only "Context and Problem
Statement" and "Decision Outcome" are emitted; inventing options nobody
considered would be exactly the kind of fabrication this pipeline's
whole "never invent, state the gap" discipline exists to avoid.

**Every file shares this generator's one title in `llms.txt`/`master.md`.**
`ProducedDocument.title` is set once per generator, not once per output
- a reader distinguishes entries by their link (the numbered filename
each one's href carries), not by the link text, until a future ticket
threads a per-output title through the pipeline. Not attempted here:
ADR-0023 doesn't ask for one, and `llms.txt`'s primary reader is an
agent parsing the raw line (title *and* href) rather than a human
skimming rendered bullets.

Details: docs/dev/generators/decisions_adr.md#module
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from .requirements import build_requirements_document

_INFERRED_CONFIDENCE = ("inferred", "assumed")

# Why this requirement's own extraction rule lands on `inferred`/`assumed`
# rather than `observed` - one entry per EARS pattern that can, keyed by
# `requirements.json`'s own `ears_pattern` field. A pattern absent here
# (a future extraction rule this table hasn't been updated for yet) falls
# back to a generic, still-honest statement rather than a fabricated one.
_CONFIDENCE_CONTEXT: Dict[str, str] = {
    "optional_feature": (
        "data-model.json observed this field declared nullable in the page's own markup - a "
        "declared-optional convention, not an observed omission. No interaction the crawl recorded "
        "actually submitted this field blank and succeeded; the classification rests on markup, "
        "not on witnessed behavior."
    ),
}

_DEFAULT_CONFIDENCE_CONTEXT = (
    "requirements.py's own extraction rule for this EARS pattern classified it below `observed` - "
    "see that module's docstring for the specific reasoning."
)


def _slug(syntax_text: str) -> str:
    """A filesystem-safe fragment of `syntax_text` for the MADR filename -
    collision is harmless (the sequential number prefix is what actually
    disambiguates two files), so this only needs to be legible, not unique.
    Details: docs/dev/generators/decisions_adr.md#_slug
    """
    slug = re.sub(r"[^a-z0-9]+", "-", syntax_text.lower()).strip("-")
    return slug[:60].rstrip("-")


def decision_entities(request: DocumentRequest) -> List[Dict[str, Any]]:
    """Every `requirements.json` entry classified `inferred`/`assumed`
    (ADR-0023 point 1), in `requirements.json`'s own deterministic id
    order - never crawl-discovery order, so numbering stays stable across
    runs of the same crawl.
    Details: docs/dev/generators/decisions_adr.md#decision_entities
    """
    document = build_requirements_document(request)
    return [r for r in document["requirements"] if r["confidence"] in _INFERRED_CONFIDENCE]


def _render_decision(number: int, requirement: Dict[str, Any]) -> str:
    """One MADR file's content - Context and Problem Statement, then
    Decision Outcome, citing the entity as a cross-reference (ADR-0023
    point 2). No Decision Drivers/Considered Options: nothing here was
    actually deliberated between named alternatives.
    Details: docs/dev/generators/decisions_adr.md#_render_decision
    """
    context = _CONFIDENCE_CONTEXT.get(requirement["ears_pattern"], _DEFAULT_CONFIDENCE_CONTEXT)
    open_questions = requirement["open_questions"]
    lines = [
        f"# {number:04d}: {requirement['syntax_text']}",
        "",
        "## Context and Problem Statement",
        "",
        context,
        "",
        "## Decision Outcome",
        "",
        f"Classified `{requirement['confidence']}`, not `observed`. Cross-reference: `{requirement['id']}` "
        "(requirements.json).",
    ]
    if open_questions:
        lines += ["", "Open question(s) this classification did not resolve:", ""]
        lines += [f"- {question}" for question in open_questions]
    lines.append("")
    return "\n".join(lines)


@DOCUMENT_REGISTRY.register("decisions.adr")
class DecisionsAdrDocument(DocumentGenerator):
    """One `DocumentOutput` per inferred/assumed requirement, each a real
    numbered MADR file inside `decisions.adr/` - docs/adr/0023.
    Details: docs/dev/generators/decisions_adr.md#decisionsadrdocument
    """

    name = "decisions.adr"
    title = "Decision Records"
    purpose = "One MADR-format record per inferred/assumed classification the crawl needed to make, citing the entity it explains."
    extension = "md"

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        entities = decision_entities(request)
        return tuple(
            DocumentOutput(
                filename=f"decisions.adr/{number:04d}-{_slug(requirement['syntax_text'])}",
                kind="projection", extension="md",
                content=_render_decision(number, requirement),
            )
            for number, requirement in enumerate(entities, 1)
        )
