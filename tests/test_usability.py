"""Unit tests for the usability audit (generators/usability.py).
Every rule is a pure function over hand-built rows."""
from core.interfaces import ComponentFamily, InferredRequest
from generators.usability import (
    inconsistent_action_naming,
    inconsistent_family_styling,
    missing_semantic_input_type,
    unexplained_disabled_controls,
)

PAGE = "shop/"


def _component(path, **facts):
    row = {
        "page_url": PAGE, "path": path, "text": "Comprar", "component_type": "button",
        "background_color": "", "name": "", "placeholder": "", "disabled": False,
        "x": 10, "y": 10,
    }
    row.update(facts)
    return row


def _family(paths, component_type="button"):
    return ComponentFamily(
        tag="button", component_type=component_type, common_classes=("btn",),
        member_paths=tuple((PAGE, path) for path in paths), purpose="",
    )


# --- consistency ---

def test_one_pattern_in_two_background_colours_is_flagged():
    """Three shades of primary button is not something anyone spots by eye
    across a large app - it takes the family grouping to see it."""
    findings = inconsistent_family_styling(
        [_family(["a", "b"])],
        [_component("a", background_color="#2d7"), _component("b", background_color="#c33")],
    )

    assert len(findings) == 1
    assert findings[0].rule == "inconsistent-family-styling"
    assert "#2d7" in findings[0].detail and "#c33" in findings[0].detail


def test_one_pattern_in_one_colour_is_not_a_finding():
    findings = inconsistent_family_styling(
        [_family(["a", "b"])],
        [_component("a", background_color="#2d7"), _component("b", background_color="#2d7")],
    )

    assert findings == []


def test_members_missing_from_the_ledger_never_produce_a_finding():
    assert inconsistent_family_styling([_family(["gone"])], []) == []


def test_one_endpoint_under_two_button_labels_is_flagged():
    request = InferredRequest(
        method="POST", endpoint="api/orders", query_params=(), body_shape="", response_shape="",
        triggered_by=((PAGE, "a"), (PAGE, "b")),
    )

    findings = inconsistent_action_naming(
        [request], [_component("a", text="Guardar"), _component("b", text="Confirmar")]
    )

    assert len(findings) == 1
    assert "'Guardar'" in findings[0].detail and "'Confirmar'" in findings[0].detail


def test_one_endpoint_under_one_label_is_not_a_finding():
    request = InferredRequest(
        method="POST", endpoint="api/orders", query_params=(), body_shape="", response_shape="",
        triggered_by=((PAGE, "a"), (PAGE, "b")),
    )

    assert inconsistent_action_naming([request], [_component("a"), _component("b")]) == []


# --- error prevention ---

def test_an_email_field_declared_as_plain_text_is_flagged():
    findings = missing_semantic_input_type(
        [_component("a", component_type="text field (text)", name="user_email")]
    )

    assert len(findings) == 1
    assert 'type="email"' in findings[0].recommendation


def test_the_hint_is_matched_accent_and_case_insensitively():
    """Accents are folded, not deleted: "móvil" has to become "movil" and
    match, not "mvil" and miss."""
    findings = missing_semantic_input_type(
        [_component("a", component_type="text field (text)", placeholder="Número de Móvil")]
    )

    assert len(findings) == 1
    assert 'type="tel"' in findings[0].recommendation


def test_a_field_already_declared_with_its_real_type_is_not_flagged():
    findings = missing_semantic_input_type(
        [_component("a", component_type="text field (email)", name="user_email")]
    )

    assert findings == []


def test_a_field_with_no_hint_in_its_name_is_left_alone():
    findings = missing_semantic_input_type(
        [_component("a", component_type="text field (text)", name="comentario")]
    )

    assert findings == []


def test_one_field_produces_at_most_one_type_finding():
    """`fecha_email` matching two vocabularies must not report twice."""
    findings = missing_semantic_input_type(
        [_component("a", component_type="text field (text)", name="fecha_email")]
    )

    assert len(findings) == 1


# --- disabled controls ---

def test_a_disabled_control_with_no_nearby_text_is_flagged():
    findings = unexplained_disabled_controls([_component("a", disabled=True)], {PAGE: []})

    assert len(findings) == 1
    assert findings[0].rule == "unexplained-disabled-control"


def test_a_disabled_control_with_text_beside_it_is_not_flagged():
    findings = unexplained_disabled_controls(
        [_component("a", disabled=True)], {PAGE: [{"x": 20, "y": 30, "text": "Completá el formulario"}]}
    )

    assert findings == []


def test_a_control_with_no_geometry_is_never_reported():
    """Reporting on a guess wastes a reviewer's time; missing one costs
    nothing, since this rule is a low-severity nicety."""
    findings = unexplained_disabled_controls(
        [_component("a", disabled=True, x=None, y=None)], {PAGE: []}
    )

    assert findings == []


def test_an_enabled_control_is_never_reported():
    assert unexplained_disabled_controls([_component("a")], {PAGE: []}) == []


# --- document ---

def test_findings_are_ordered_by_severity():
    from core.documents import DocumentRequest
    from generators.usability import build_findings

    class _Store:
        def get_component_ledger(self, site):
            return {PAGE: {
                "a": _component("a", background_color="#2d7"),
                "b": _component("b", background_color="#c33"),
                "c": _component("c", disabled=True),
            }}

        def get_edges(self, site):
            return []

        def get_component_families(self, site):
            return [_family(["a", "b"])]

        def get_inferred_requests(self, site):
            return []

        def get_text_content_ledger(self, site):
            return {PAGE: []}

    findings = build_findings(DocumentRequest(graph_store=_Store(), site="shop.example", agent=None))

    assert [f.severity for f in findings] == ["medium", "low"]


def test_an_empty_audit_says_what_it_did_not_check():
    """"No findings" from six rules must not read as "this app is usable"."""
    from core.documents import DocumentRequest
    from generators.usability import UsabilityDocument

    class _Store:
        def get_component_ledger(self, site):
            return {}

        def get_edges(self, site):
            return []

        def get_component_families(self, site):
            return []

        def get_inferred_requests(self, site):
            return []

        def get_text_content_ledger(self, site):
            return {}

    text = UsabilityDocument().generate(
        DocumentRequest(graph_store=_Store(), site="shop.example", agent=None)
    )

    assert "narrow statement" in text
