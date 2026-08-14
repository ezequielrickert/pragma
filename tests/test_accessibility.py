"""Unit tests for the accessibility document (generators/accessibility.py)
and the measurement pass's page selection. No browser: axe's own output is
fed in as the fixtures it produces."""
from spiders.orchestration.measurement_pass import _navigable, _pages_to_measure
from generators.accessibility import (
    MINIMUM_TARGET_PX,
    build_axe_findings,
    undersized_targets,
)

PAGE = "shop.example/cart"


def _violation(rule_id="color-contrast", impact="serious", nodes=None, total=None):
    nodes = nodes if nodes is not None else [{"path": "div > button", "axe_target": "#a", "summary": ""}]
    return {
        "rule_id": rule_id, "impact": impact, "help": "Elements must have sufficient colour contrast",
        "help_url": "https://dequeuniversity.com/rules/axe/4.10/color-contrast",
        "criteria": ["wcag2aa", "wcag143"], "nodes": nodes,
        "total_nodes": total if total is not None else len(nodes),
    }


def _component(path="div > button", width=40, height=40, layer="semantic"):
    return {"page_url": PAGE, "path": path, "width": width, "height": height, "layer": layer}


# --- axe findings ---

def test_a_violation_becomes_a_finding_with_its_criteria():
    findings = build_axe_findings({PAGE: [_violation()]})

    assert len(findings) == 1
    assert findings[0].rule_id == "color-contrast"
    assert findings[0].criteria == ("wcag2aa", "wcag143")


def test_findings_are_ordered_by_impact_then_reach():
    findings = build_axe_findings({
        PAGE: [
            _violation(rule_id="minor-thing", impact="minor"),
            _violation(rule_id="critical-thing", impact="critical"),
            _violation(rule_id="serious-thing", impact="serious"),
        ]
    })

    assert [f.rule_id for f in findings] == ["critical-thing", "serious-thing", "minor-thing"]


def test_the_element_count_is_the_real_total_not_the_capped_sample():
    """axe's per-rule node list is capped before storage; reporting the cap
    as the count would understate a defect hitting hundreds of elements."""
    findings = build_axe_findings({PAGE: [_violation(nodes=[{"path": "a"}] * 25, total=300)]})

    assert findings[0].element_count == 300
    assert len(findings[0].resolved_paths) == 25


def test_elements_axe_reported_but_that_did_not_resolve_are_counted_separately():
    """A selector that resolves to nothing of ours is still a real finding -
    it just cannot be pointed at a component node."""
    findings = build_axe_findings({
        PAGE: [_violation(nodes=[{"path": "div > button"}, {"path": ""}, {"path": ""}])]
    })

    assert findings[0].resolved_paths == ("div > button",)
    assert findings[0].unresolved == 2


def test_no_audit_produces_no_findings():
    assert build_axe_findings({}) == []


# --- our own target-size rule ---

def test_a_control_smaller_than_the_minimum_is_flagged():
    findings = undersized_targets([_component(width=16, height=16)])

    assert len(findings) == 1
    assert findings[0].rule_id == "target-size"


def test_a_control_at_the_minimum_is_not_flagged():
    assert undersized_targets([_component(width=MINIMUM_TARGET_PX, height=MINIMUM_TARGET_PX)]) == []


def test_a_control_with_no_recorded_size_is_not_assumed_small():
    """A missing measurement is not a small one."""
    assert undersized_targets([_component(width=None, height=None)]) == []


def test_pointer_layer_elements_are_excluded():
    """The cursor:pointer catch-all layer is a discovery net, not a list of
    real controls - flagging its members would bury the real findings."""
    assert undersized_targets([_component(width=4, height=4, layer="pointer")]) == []


def test_one_finding_per_page_gathers_every_small_control_on_it():
    findings = undersized_targets([
        _component(path="a", width=10, height=10),
        _component(path="b", width=12, height=12),
    ])

    assert len(findings) == 1
    assert findings[0].element_count == 2


# --- measurement-pass page selection ---

def test_a_shaped_route_cannot_be_re_visited():
    """Page nodes are keyed by route_shape, so a page whose path held an
    opaque token is stored as a shape, not an address."""
    assert _navigable("shop.example/o/{token}") is False
    assert _navigable("shop.example/cart") is True


def test_only_finished_pages_are_measured_and_shaped_ones_are_reported():
    class _Store:
        def get_progress_table_rows(self, site):
            return [
                {"url": "shop.example/cart", "status": "Finished"},
                {"url": "shop.example/o/{token}", "status": "Finished"},
                {"url": "shop.example/never", "status": "Pending"},
            ]

    navigable, shaped = _pages_to_measure(_Store(), "shop.example")

    assert navigable == ["shop.example/cart"]
    assert shaped == ["shop.example/o/{token}"]


# --- document ---

def test_an_unrun_measurement_pass_is_not_reported_as_a_clean_result():
    from core.documents import DocumentRequest
    from generators.accessibility import AccessibilityDocument

    class _Store:
        def get_accessibility_violations(self, site):
            return {}

        def get_page_measurements(self, site):
            return {}

        def get_component_ledger(self, site):
            return {}

    text = AccessibilityDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "No page was audited" in text
    assert "not the same as a clean result" in text


def test_the_document_states_what_automation_cannot_find():
    from core.documents import DocumentRequest
    from generators.accessibility import AccessibilityDocument

    class _Store:
        def get_accessibility_violations(self, site):
            return {PAGE: [_violation()]}

        def get_page_measurements(self, site):
            return {}

        def get_component_ledger(self, site):
            return {}

    text = AccessibilityDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "a clean report is not a compliant application" in text.lower()
    # Keyboard operation is covered now (see keyboard_findings); what stays
    # out is anything needing human judgement.
    assert "not automatable" in text
    assert "div > button" in text


# --- keyboard walk (Fase 8) ---

def _stop(path, dom_index=0, focus_visible=True, offscreen=False):
    return {"path": path, "dom_index": dom_index, "focus_visible": focus_visible, "offscreen": offscreen}


def test_a_control_focused_with_no_visible_indicator_is_flagged():
    """The common failure: a reset stylesheet removing the UA outline and
    never putting anything back."""
    from generators.accessibility import keyboard_findings

    findings = keyboard_findings({PAGE: {"tab_order": [_stop("a", focus_visible=False)]}})

    assert [f.rule_id for f in findings] == ["focus-visible"]
    assert findings[0].criteria == ("wcag21aa", "wcag247")


def test_a_tab_order_that_goes_backwards_is_flagged():
    """Unreachable by reading the DOM, which is why the pass presses real
    keys - it is usually a positive tabindex."""
    from generators.accessibility import keyboard_findings

    findings = keyboard_findings({PAGE: {"tab_order": [_stop("a", 5), _stop("b", 1)]}})

    assert "focus-order" in [f.rule_id for f in findings]


def test_a_tab_order_that_follows_the_document_is_not_flagged():
    from generators.accessibility import keyboard_findings

    findings = keyboard_findings({PAGE: {"tab_order": [_stop("a", 0), _stop("b", 1), _stop("c", 2)]}})

    assert findings == []


def test_focus_landing_on_something_with_no_size_is_flagged():
    from generators.accessibility import keyboard_findings

    findings = keyboard_findings({PAGE: {"tab_order": [_stop("a", 0, offscreen=True)]}})

    assert "focus-offscreen" in [f.rule_id for f in findings]


def test_a_page_with_no_keyboard_walk_produces_nothing():
    from generators.accessibility import keyboard_findings

    assert keyboard_findings({PAGE: {"tab_order": []}}) == []
