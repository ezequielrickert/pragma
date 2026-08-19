"""D11: accessibility findings that can be computed from what the crawl
already captures, without axe-core.

**This is deliberately a partial WCAG audit, and says so in its own output.**
The previous D11 ran axe-core (~90 rules) during a measurement pass that no
longer exists. Rather than leave the project with no accessibility document at
all, this covers the criteria the captured data supports *deterministically* -
accessible names and landmark structure - and names the ones it cannot reach.

What makes these computable now and not before:

- `discover_components.js` already resolves the full accessible-name chain
  (`innerText` -> `aria-label` -> `aria-labelledby` -> `title` -> `img[alt]` ->
  `svg > title`) into `text`, and the `<label>` association separately into
  `label`. A control whose name is empty after all of that is a finding, not a
  guess.
- `Container.landmark` and `get_page_landmarks()` make landmark structure a
  queryable property of the page.

What it cannot do, and why the gap is about capture rather than storage:
contrast ratios need stacked-background resolution (`background_color` reports
`rgba(0,0,0,0)` for any element whose background an ancestor paints, which is
most of them); touch-target size and spacing are absolute thresholds against
geometry measured at 800x600 with images blocked; focus visibility and tab
order need a pass that drives the keyboard. All three need the measurement
pass - see `research/plan-segunda-ronda-de-documentos.md` B2/nivel 3.

Findings are not stored. Same as D7: they are recomputed deterministically from
the graph every run, the document is their only consumer, and `Rule` nodes with
`DERIVED_FROM` are there for the day a second one appears.

Details: docs/dev/generators/accessibility.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from .ledger import flat_component_ledger

# Landmark roles a page may only have one of. `navigation` and `region` are
# deliberately absent: several navs is normal and correct markup.
# Details: docs/dev/generators/accessibility.md#_unique_landmarks
_UNIQUE_LANDMARKS: Tuple[str, ...] = ("banner", "main", "contentinfo")

# Component types that are operable and therefore need an accessible name.
# `element` and the pointer-layer catch-all are excluded - see
# `_needs_a_name` for why that exclusion is a floor and not a dismissal.
# Details: docs/dev/generators/accessibility.md#_named_component_types
_NAMED_COMPONENT_TYPES: Tuple[str, ...] = (
    "button", "submit button", "link", "checkbox", "radio button", "toggle switch",
    "tab", "native dropdown (select)", "combobox", "text field",
)


@dataclass(frozen=True)
class AccessibilityFinding:
    """One finding, with the criterion it fails and the evidence to check it.
    Details: docs/dev/generators/accessibility.md#accessibilityfinding
    """

    rule: str
    criterion: str
    severity: str
    where: str
    detail: str
    recommendation: str


def _needs_a_name(component: Dict[str, Any]) -> bool:
    """Whether this component is operable enough to require a name.

    Restricted to the semantic discovery layer. A `cursor: pointer` catch-all
    element with no tag or role of its own may well be an unnamed clickable div
    - a real 4.1.2 failure - but it may equally be a decorative wrapper that
    merely inherits a cursor, and the crawl cannot tell those apart. Reporting
    every one of them buries the findings that are certain. The document states
    how many were skipped rather than leaving the exclusion invisible.
    Details: docs/dev/generators/accessibility.md#_needs_a_name
    """
    if component.get("layer") == "pointer":
        return False
    component_type = (component.get("component_type") or "").lower()
    return any(component_type.startswith(prefix) for prefix in _NAMED_COMPONENT_TYPES)


def accessible_name(component: Dict[str, Any]) -> str:
    """The name assistive technology would announce, or `""`.

    Two sources, both already captured: `text` (the resolved
    innerText/aria-label/title/alt chain) and `label` (the `<label>` element
    association). Either satisfies WCAG - an `aria-label` is a programmatic
    label, so a field named that way is not a finding.

    `placeholder` is **not** a source. It disappears on input, is not announced
    consistently, and treating it as a name is the failure
    `placeholder-as-only-label` reports.
    Details: docs/dev/generators/accessibility.md#accessible_name
    """
    return ((component.get("text") or "").strip() or (component.get("label") or "").strip())


def name_findings(components: Sequence[Dict[str, Any]]) -> List[AccessibilityFinding]:
    """The two accessible-name rules, most specific first.

    A nameless field that does have a placeholder gets the specific
    `placeholder-as-only-label` finding rather than the generic one: the fix
    differs (promote the placeholder to a label, versus invent a name), and
    reporting both for one element would double-count it.
    Details: docs/dev/generators/accessibility.md#name_findings
    """
    findings = []
    for component in components:
        if not _needs_a_name(component) or accessible_name(component):
            continue
        where = f"{component.get('page_url')} — {component.get('path')}"
        component_type = component.get("component_type") or "control"
        if (component.get("placeholder") or "").strip():
            findings.append(
                AccessibilityFinding(
                    rule="placeholder-as-only-label",
                    criterion="WCAG 3.3.2 Labels or Instructions",
                    severity="medium",
                    where=where,
                    detail=f"{component_type} whose only visible name is its placeholder "
                           f"({component['placeholder']!r}).",
                    recommendation="Give it a real `<label>` in the rebuild. A placeholder "
                                   "disappears as soon as the user types, so it cannot be the name.",
                )
            )
            continue
        findings.append(
            AccessibilityFinding(
                rule="missing-accessible-name",
                criterion="WCAG 4.1.2 Name, Role, Value",
                severity="high",
                where=where,
                detail=f"{component_type} with no accessible name: no text, no `aria-label`, "
                       "no `aria-labelledby`, no `title`, no associated `<label>`.",
                recommendation="Give it a visible text label, or `aria-label` when the design "
                               "needs it to stay icon-only. A screen reader announces this "
                               "control as nothing at all today.",
            )
        )
    return findings


def landmark_findings(landmarks: Dict[str, Dict[str, int]]) -> List[AccessibilityFinding]:
    """Structural rules, one per page with a landmark problem.

    Only pages that reported at least one landmark are judged. A page absent
    from `get_page_landmarks()` has no recorded ancestry at all, and "this page
    has no main region" and "containment was never captured for this page" are
    not the same claim.
    Details: docs/dev/generators/accessibility.md#landmark_findings
    """
    findings = []
    for page_url in sorted(landmarks):
        counts = landmarks[page_url]
        if not counts.get("main"):
            findings.append(
                AccessibilityFinding(
                    rule="no-main-landmark",
                    criterion="WCAG 2.4.1 Bypass Blocks",
                    severity="medium",
                    where=page_url,
                    detail="The page has landmark regions but none of them is `main`.",
                    recommendation="Wrap the primary content in `<main>` so keyboard and screen "
                                   "reader users can skip the header and navigation.",
                )
            )
        for landmark in _UNIQUE_LANDMARKS:
            count = counts.get(landmark, 0)
            if count > 1:
                findings.append(
                    AccessibilityFinding(
                        rule="duplicate-unique-landmark",
                        criterion="WCAG 1.3.1 Info and Relationships",
                        severity="low",
                        where=page_url,
                        detail=f"{count} separate `{landmark}` regions on one page.",
                        recommendation=f"Keep one `{landmark}` per page, or give each a distinct "
                                       "accessible name so they can be told apart.",
                    )
                )
    return findings


def build_findings(request: DocumentRequest) -> Tuple[List[AccessibilityFinding], int]:
    """Every rule over one site's graph, plus how many components were skipped.

    The skipped count is returned rather than logged: it is the size of this
    document's own blind spot, and belongs in the document.
    Details: docs/dev/generators/accessibility.md#build_findings
    """
    store = request.graph_store
    components = flat_component_ledger(store)
    skipped = sum(1 for component in components if component.get("layer") == "pointer")
    findings = name_findings(components) + landmark_findings(store.get_page_landmarks())
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (order.get(f.severity, 3), f.rule, f.where))
    return findings, skipped


_SCOPE_NOTE = (
    "**This is a partial audit, not a conformance check.** It covers the criteria the crawl's "
    "captured data supports deterministically: accessible names and landmark structure. Contrast "
    "ratios, touch-target sizes, focus visibility and tab order are absent - each needs a "
    "measurement pass that visits pages at a realistic viewport with images enabled, which this "
    "pipeline does not have. A clean report here does not mean the application is accessible."
)


@DOCUMENT_REGISTRY.register("accessibility")
class AccessibilityDocument(DocumentGenerator):
    """Details: docs/dev/generators/accessibility.md#accessibilitydocument"""

    name = "accessibility"
    title = "Accessibility Audit"
    purpose = "Deterministic WCAG findings on accessible names and landmark structure, each tied to the element that fails."

    def generate(self, request: DocumentRequest) -> str:
        findings, skipped = build_findings(request)
        lines = [f"# Accessibility Audit: {request.site}", "", _SCOPE_NOTE, ""]
        if skipped:
            lines += [
                f"{skipped} element(s) found only by the `cursor: pointer` catch-all are excluded "
                "from the name rules. An unnamed clickable `div` is a real failure and a decorative "
                "wrapper is not, and the crawl cannot tell them apart - so they are counted here "
                "rather than reported as either.",
                "",
            ]
        if not findings:
            lines += [
                "No findings from these rules. Read that narrowly: it means every operable control "
                "the crawl found has a name and every page with landmarks has a `main`.",
                "",
            ]
            return "\n".join(lines)
        lines += [
            f"{len(findings)} finding(s), worst first. Each cites the page and element it came "
            "from - disagree and go look.",
            "",
            "| Severity | Rule | Criterion | Where | Finding | Do instead |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {f.severity} | `{f.rule}` | {f.criterion} | {f.where} | {f.detail} | {f.recommendation} |"
            for f in findings
        ]
        lines.append("")
        return "\n".join(lines)
