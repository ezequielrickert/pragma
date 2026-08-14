"""D11: WCAG 2.1 A/AA findings from axe-core, plus the one rule axe does
not ship.

Separate from the usability audit on purpose: this has a named standard,
numbered criteria and a different audience. A developer fixing `4.1.2` and
a designer weighing "is this confusing" are not reading the same document.

The engine is axe-core (Deque, MPL-2.0), vendored unmodified and run by
the measurement pass. Writing these rules by hand was the earlier plan and
was wrong: the contrast check alone has to resolve stacked backgrounds,
opacity and gradients, and a first attempt at it here would have read
`background_color` off the element itself - which is `rgba(0,0,0,0)` for
almost every element, since the colour comes from an ancestor.

Details: docs/dev/generators/accessibility.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from .ledger import flat_component_ledger

# WCAG 2.2 minimum for a pointer target, in CSS pixels. Kept as our own
# rule: axe's `target-size` is not in its stable rule set, and the geometry
# to check it is already in the graph.
# Details: docs/dev/generators/accessibility.md#target_size
MINIMUM_TARGET_PX = 24

_IMPACT_ORDER = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}

_COVERAGE_NOTE = (
    "Automated testing finds on the order of a third of real WCAG problems. Everything here is a "
    "genuine violation - axe reports only what it can determine without judgement - but a clean "
    "report is not a compliant application. Judgement-dependent criteria (is this label clear, is "
    "this order logical to a person) are not automatable and are absent."
)


@dataclass(frozen=True)
class AccessibilityFinding:
    """One violated rule on one page.
    Details: docs/dev/generators/accessibility.md#accessibilityfinding
    """

    page_url: str
    rule_id: str
    impact: str
    criteria: Tuple[str, ...]
    help: str
    help_url: str
    element_count: int
    resolved_paths: Tuple[str, ...]
    unresolved: int


def _finding_from(page_url: str, violation: Dict[str, Any]) -> AccessibilityFinding:
    nodes = violation.get("nodes") or []
    resolved = [node.get("path") for node in nodes if node.get("path")]
    return AccessibilityFinding(
        page_url=page_url,
        rule_id=violation.get("rule_id", ""),
        impact=violation.get("impact", ""),
        criteria=tuple(violation.get("criteria") or []),
        help=violation.get("help", ""),
        help_url=violation.get("help_url", ""),
        element_count=int(violation.get("total_nodes") or len(nodes)),
        resolved_paths=tuple(resolved),
        unresolved=len(nodes) - len(resolved),
    )


def build_axe_findings(violations_by_page: Dict[str, List[Dict[str, Any]]]) -> List[AccessibilityFinding]:
    """Flatten the stored audit into one finding per (page, rule).
    Details: docs/dev/generators/accessibility.md#build_axe_findings
    """
    findings = [
        _finding_from(page_url, violation)
        for page_url, violations in violations_by_page.items()
        for violation in violations
    ]
    return sorted(
        findings, key=lambda f: (_IMPACT_ORDER.get(f.impact, 4), -f.element_count, f.page_url, f.rule_id)
    )


def undersized_targets(components: Sequence[Dict[str, Any]]) -> List[AccessibilityFinding]:
    """Controls too small to hit reliably - WCAG 2.2 criterion 2.5.8.

    Ours rather than axe's, because axe's `target-size` rule is not in its
    stable set and the geometry is already in the graph. Skips components
    with no recorded size rather than assuming: a missing measurement is
    not a small one.
    Details: docs/dev/generators/accessibility.md#target_size
    """
    by_page: Dict[str, List[str]] = {}
    for component in components:
        width, height = component.get("width"), component.get("height")
        if width is None or height is None or component.get("layer") == "pointer":
            continue
        if width >= MINIMUM_TARGET_PX and height >= MINIMUM_TARGET_PX:
            continue
        by_page.setdefault(component.get("page_url", ""), []).append(component.get("path", ""))

    return [
        AccessibilityFinding(
            page_url=page_url,
            rule_id="target-size",
            impact="moderate",
            criteria=("wcag22aa", "wcag258"),
            help=f"Pointer target smaller than {MINIMUM_TARGET_PX}x{MINIMUM_TARGET_PX} CSS pixels.",
            help_url="https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html",
            element_count=len(paths),
            resolved_paths=tuple(sorted(paths)[:25]),
            unresolved=0,
        )
        for page_url, paths in sorted(by_page.items())
    ]


def keyboard_findings(measurements: Dict[str, Dict[str, Any]]) -> List[AccessibilityFinding]:
    """What the Tab walk found: invisible focus, and a tab order that
    disagrees with reading order.

    Neither is reachable by reading the DOM, which is the whole reason the
    measurement pass presses real keys. A tab order matching source order
    is the default; one that does not is usually a positive `tabindex`,
    and it is invisible to any check that walks the document instead.
    Details: docs/dev/generators/accessibility.md#keyboard_findings
    """
    findings: List[AccessibilityFinding] = []
    for page_url, page in sorted(measurements.items()):
        stops = page.get("tab_order") or []
        if not stops:
            continue

        invisible = [stop["path"] for stop in stops if not stop.get("focus_visible")]
        if invisible:
            findings.append(
                AccessibilityFinding(
                    page_url=page_url, rule_id="focus-visible", impact="serious",
                    criteria=("wcag21aa", "wcag247"),
                    help="Focused control shows no visible focus indicator.",
                    help_url="https://www.w3.org/WAI/WCAG21/Understanding/focus-visible.html",
                    element_count=len(invisible), resolved_paths=tuple(invisible[:25]), unresolved=0,
                )
            )

        # A stop whose DOM position goes backwards relative to the previous
        # one means Tab jumped against reading order.
        indexes = [stop.get("dom_index", -1) for stop in stops]
        out_of_order = [
            stops[i]["path"]
            for i in range(1, len(indexes))
            if indexes[i] >= 0 and indexes[i - 1] >= 0 and indexes[i] < indexes[i - 1]
        ]
        if out_of_order:
            findings.append(
                AccessibilityFinding(
                    page_url=page_url, rule_id="focus-order", impact="moderate",
                    criteria=("wcag2a", "wcag243"),
                    help="Tab order does not follow the order the content is written in.",
                    help_url="https://www.w3.org/WAI/WCAG21/Understanding/focus-order.html",
                    element_count=len(out_of_order), resolved_paths=tuple(out_of_order[:25]), unresolved=0,
                )
            )

        offscreen = [stop["path"] for stop in stops if stop.get("offscreen")]
        if offscreen:
            findings.append(
                AccessibilityFinding(
                    page_url=page_url, rule_id="focus-offscreen", impact="serious",
                    criteria=("wcag2a", "wcag241"),
                    help="Tab moves focus to a control with no size on screen - a keyboard user "
                         "loses their place with nothing to see.",
                    help_url="https://www.w3.org/WAI/WCAG21/Understanding/no-keyboard-trap.html",
                    element_count=len(offscreen), resolved_paths=tuple(offscreen[:25]), unresolved=0,
                )
            )
    return findings


@DOCUMENT_REGISTRY.register("accessibility")
class AccessibilityDocument(DocumentGenerator):
    """Details: docs/dev/generators/accessibility.md#accessibilitydocument"""

    name = "accessibility"
    title = "Accessibility Audit"
    purpose = "WCAG 2.1 A/AA violations found by axe-core, each tied to the element that fails."

    def generate(self, request: DocumentRequest) -> str:
        violations = request.graph_store.get_accessibility_violations(request.site)
        measurements = request.graph_store.get_page_measurements(request.site)
        components = flat_component_ledger(request.graph_store, request.site)
        findings = (
            build_axe_findings(violations)
            + keyboard_findings(measurements)
            + undersized_targets(components)
        )

        lines = [f"# Accessibility Audit: {request.site}", ""]
        if not violations:
            lines += [
                "No page was audited. The audit runs in the measurement pass, which re-visits the "
                "crawled pages with a realistic browser - if that pass has not run, this document "
                "has nothing to report and that is not the same as a clean result.",
                "",
            ]
            if not findings:
                return "\n".join(lines)

        lines += [_COVERAGE_NOTE, "", f"{len(findings)} rule violations across "
                  f"{len({f.page_url for f in findings})} pages.", ""]
        lines += ["| Impact | Rule | Criteria | Page | Elements | What fails |", "|---|---|---|---|---|---|"]
        for finding in findings:
            criteria = ", ".join(finding.criteria) or "-"
            help_text = f"[{finding.help}]({finding.help_url})" if finding.help_url else finding.help
            lines.append(
                f"| {finding.impact or '-'} | `{finding.rule_id}` | {criteria} | {finding.page_url} "
                f"| {finding.element_count} | {help_text} |"
            )
        lines.append("")

        detailed = [f for f in findings if f.resolved_paths]
        if detailed:
            lines += ["## Failing elements", "",
                      "Resolved to the same CSS paths the graph uses, so each one is a node you can "
                      "look up rather than a selector to go hunting for. `(document)` means the rule is "
                      "about the page itself, not an element on it.", ""]
            for finding in detailed:
                lines.append(f"**`{finding.rule_id}` on {finding.page_url}**")
                lines += [f"- `{path}`" for path in finding.resolved_paths]
                if finding.unresolved:
                    lines.append(
                        f"- _(+{finding.unresolved} elements axe reported that did not resolve to a "
                        "known component - most often inside a frame or removed after the audit)_"
                    )
                lines.append("")
        return "\n".join(lines)
