"""D7: usability findings against Nielsen's heuristics, computed rather
than judged.

Every rule here is deterministic and every finding carries the page and
element it came from - a reader who disagrees can go look. No model call:
a heuristic evaluation the model performs is an opinion, and an opinion
that cites no evidence is not worth putting in a document a rebuild will
be planned from.

**Findings are prescriptive.** "The button has no label" describes the
past; the goal is to refactor the experience, not to reproduce it, so each
finding says what the rebuild should do instead.

Pure detection logic only - `generators/usability_act.py` owns the
ACT/EARL/SARIF serialization (docs/adr/0011) and the registered
`DocumentGenerator`, the same `build_X`/adapter split every other
generator here uses.

Details: docs/dev/generators/usability.md#module
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from core.documents import DocumentRequest
from .ledger import flat_component_ledger
from .user_flows import build_flow_graph

# Field-name/placeholder vocabulary implying a more specific input type
# than plain text. Matched against `name` and `placeholder`, accent-free.
# Details: docs/dev/generators/usability.md#_semantic_type_hints
_SEMANTIC_TYPE_HINTS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("email", ("email", "correo", "mail")),
    ("tel", ("tel", "telefono", "phone", "celular", "movil")),
    ("date", ("date", "fecha", "birth", "nacimiento")),
    ("number", ("cantidad", "quantity", "amount", "monto", "cuit", "dni")),
    ("url", ("url", "website", "sitio")),
)

# How far from a disabled control text may sit and still count as its
# explanation, in CSS pixels. Generous on purpose: a false "no explanation"
# finding wastes a reviewer's time, a missed one costs nothing here.
_NEARBY_TEXT_PX = 120


@dataclass(frozen=True)
class Finding:
    """One usability observation, with the evidence to check it.
    Details: docs/dev/generators/usability.md#finding
    """

    rule: str
    heuristic: str
    severity: str
    where: str
    detail: str
    recommendation: str


def _normalize(text: str) -> str:
    """Accent-folded, punctuation-free comparison key.

    Folds rather than deletes: `"móvil"` must become `"movil"` and match
    the hint, not `"mvil"` and miss it. Same NFKD decomposition
    `component_classifier._normalize` already uses for its own vocabulary
    matching.
    """
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", folded.lower())


def _by_family(
    families: Sequence[Any], components: Sequence[Dict[str, Any]]
) -> Iterable[Tuple[Any, List[Dict[str, Any]]]]:
    by_key = {(c.get("page_url"), c.get("path")): c for c in components}
    for family in families:
        members = [by_key[key] for key in family.member_paths if key in by_key]
        if members:
            yield family, members


def inconsistent_family_styling(families: Sequence[Any], components: Sequence[Dict[str, Any]]) -> List[Finding]:
    """Controls the clustering already judged to be the same pattern, wearing
    different background colours.

    Only computable *because* families exist: three different shades of
    primary button is not something anyone spots by eye across a large
    application, and here it is one grouping away.
    Details: docs/dev/generators/usability.md#inconsistent_family_styling
    """
    findings = []
    for family, members in _by_family(families, components):
        colours = sorted({m.get("background_color") or "" for m in members if m.get("background_color")})
        if len(colours) < 2:
            continue
        findings.append(
            Finding(
                rule="inconsistent-family-styling",
                heuristic="Consistency and standards",
                severity="medium",
                where=f"{family.component_type} ({len(members)} instances)",
                detail=f"Same component pattern rendered in {len(colours)} background colours: {', '.join(colours)}.",
                recommendation="Pick one token per semantic variant and bind every instance to it; "
                               "the design-token document lists the colours actually in use.",
            )
        )
    return findings


def inconsistent_action_naming(requests: Sequence[Any], components: Sequence[Dict[str, Any]]) -> List[Finding]:
    """One endpoint invoked by controls that call themselves different things.

    Two buttons doing literally the same thing under two names is a
    consistency defect a user pays for, and it is invisible without the
    endpoint to group them by.
    Details: docs/dev/generators/usability.md#inconsistent_action_naming
    """
    by_key = {(c.get("page_url"), c.get("path")): c for c in components}
    findings = []
    for request in requests:
        labels = sorted({
            (by_key[key].get("text") or "").strip()
            for key in request.triggered_by
            if key in by_key and (by_key[key].get("text") or "").strip()
        })
        if len(labels) < 2:
            continue
        findings.append(
            Finding(
                rule="inconsistent-action-naming",
                heuristic="Consistency and standards",
                severity="medium",
                where=f"{request.method} {request.endpoint}",
                detail=f"One endpoint triggered by controls labelled: {', '.join(repr(l) for l in labels)}.",
                recommendation="Name the same action the same way everywhere, or split the endpoint if "
                               "the actions really differ.",
            )
        )
    return findings


def missing_semantic_input_type(components: Sequence[Dict[str, Any]]) -> List[Finding]:
    """A field asking for an email in a plain text box.

    Costs the user the right keyboard on mobile and the browser's own
    validation, both free with the correct `type`.
    Details: docs/dev/generators/usability.md#missing_semantic_input_type
    """
    findings = []
    for component in components:
        component_type = component.get("component_type") or ""
        if not component_type.startswith("text field (text"):
            continue
        haystack = _normalize(f"{component.get('name', '')} {component.get('placeholder', '')}")
        for expected, hints in _SEMANTIC_TYPE_HINTS:
            if not any(hint in haystack for hint in hints):
                continue
            findings.append(
                Finding(
                    rule="missing-semantic-input-type",
                    heuristic="Error prevention",
                    severity="medium",
                    where=f"{component.get('page_url')} — {component.get('path')}",
                    detail=f"Field named/labelled for {expected} but declared as plain text.",
                    recommendation=f"Declare `type=\"{expected}\"` in the rebuild so the browser validates it "
                                   "and mobile shows the right keyboard.",
                )
            )
            break
    return findings


def _has_text_near(entry: Dict[str, Any], texts: Sequence[Dict[str, Any]]) -> bool:
    x, y = entry.get("x"), entry.get("y")
    if x is None or y is None:
        return True  # No geometry to judge with - never report on a guess.
    for text in texts:
        tx, ty = text.get("x"), text.get("y")
        if tx is None or ty is None:
            continue
        if abs(tx - x) <= _NEARBY_TEXT_PX and abs(ty - y) <= _NEARBY_TEXT_PX:
            return True
    return False


def unexplained_disabled_controls(
    components: Sequence[Dict[str, Any]], text_ledger: Dict[str, List[Dict[str, Any]]]
) -> List[Finding]:
    """A control the user cannot press, with nothing nearby saying why.
    Details: docs/dev/generators/usability.md#unexplained_disabled_controls
    """
    findings = []
    for component in components:
        if not component.get("disabled"):
            continue
        if _has_text_near(component, text_ledger.get(component.get("page_url", ""), [])):
            continue
        findings.append(
            Finding(
                rule="unexplained-disabled-control",
                heuristic="Help users recognise, diagnose and recover from errors",
                severity="low",
                where=f"{component.get('page_url')} — {component.get('path')}",
                detail=f"Disabled {component.get('component_type') or 'control'} with no text within "
                       f"{_NEARBY_TEXT_PX}px explaining why.",
                recommendation="State the precondition next to the control, or on it, rather than leaving "
                               "the user to guess what unlocks it.",
            )
        )
    return findings


def flow_findings(flow: Any) -> List[Finding]:
    """The rule that reads the state machine rather than a component.
    Details: docs/dev/generators/usability.md#flow_findings
    """
    findings = [
        Finding(
            rule="dead-end-screen",
            heuristic="User control and freedom",
            severity="medium",
            where=state,
            detail="No interaction the crawl tried led anywhere from this screen.",
            recommendation="Give the screen an explicit way back or forward. If the crawl simply never "
                           "reached its exits, the coverage document will say so - check before acting.",
        )
        for state in flow.dead_ends
    ]
    # `unattributable-outcome` used to be the second rule here, firing on
    # transitions whose outcome was "mixed". That outcome no longer exists:
    # a Request now hangs off its own Interaction, so `_request_outcome`
    # returns only OK/ERROR/UNKNOWN and each click of one control keeps its
    # own result. The rule described a limitation of the storage, and the
    # storage stopped having it - deleted rather than left as a branch that
    # can never be taken.
    # Details: docs/dev/generators/usability.md#flow_findings
    return findings


def build_findings(request: DocumentRequest) -> List[Finding]:
    """Every rule, over one site's graph.
    Details: docs/dev/generators/usability.md#build_findings
    """
    store = request.graph_store
    components = flat_component_ledger(store)
    flow = build_flow_graph(store.get_edges(), components)
    findings = (
        inconsistent_family_styling(store.get_component_families(), components)
        + inconsistent_action_naming(store.get_inferred_requests(), components)
        + missing_semantic_input_type(components)
        + unexplained_disabled_controls(components, store.get_text_content_ledger())
        + flow_findings(flow)
    )
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda f: (order.get(f.severity, 3), f.rule, f.where))
