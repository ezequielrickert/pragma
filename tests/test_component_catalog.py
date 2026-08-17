"""Unit tests for the component catalogue (generators/component_catalog.py).
Pure functions over hand-built families and ledger rows - no store, no model."""
import json

from core.interfaces import ComponentFamily
from generators.component_catalog import build_catalog, component_name

PAGE = "shop/"


def _member(path, css_class="btn", text="Comprar", **facts):
    row = {
        "page_url": PAGE, "path": path, "tag": "button", "text": text,
        "css_class": css_class, "background_color": "", "label": "", "placeholder": "",
        "name": "", "href": "", "form": "", "required": False, "disabled": False,
        "option_labels": [],
    }
    row.update(facts)
    return row


def _family(paths, tag="button", component_type="button", common=("btn",), purpose=""):
    return ComponentFamily(
        tag=tag, component_type=component_type, common_classes=tuple(common),
        member_paths=tuple((PAGE, path) for path in paths), purpose=purpose,
    )


# --- naming ---

def test_a_single_word_parenthetical_discriminates_and_is_kept():
    """type=email and type=password really are different components."""
    assert component_name("text field (email)") == "TextFieldEmail"


def test_a_longer_parenthetical_is_prose_and_is_dropped():
    assert component_name("combobox (searchable dropdown)") == "Combobox"
    assert component_name("custom control (component-library element, no native tag/role)") == "CustomControl"


def test_plain_labels_become_pascal_case():
    assert component_name("submit button") == "SubmitButton"


def test_colliding_names_are_disambiguated():
    catalog = build_catalog(
        [_family(["a"], tag="button"), _family(["b"], tag="div")],
        [_member("a"), _member("b", **{"tag": "div"})],
    )

    assert sorted(entry.name for entry in catalog) == ["Button", "Button2"]


# --- props ---

def test_only_fields_some_member_actually_carries_become_props():
    catalog = build_catalog(
        [_family(["a", "b"])],
        [_member("a", label="Buscar"), _member("b", label="")],
    )

    assert [p.name for p in catalog[0].props] == ["label"]


def test_a_field_identical_on_every_instance_is_marked_as_not_varying():
    """A fixed trait and a real prop look the same in the data - the
    difference is whether any instance disagrees."""
    catalog = build_catalog(
        [_family(["a", "b"])],
        [_member("a", required=True), _member("b", required=True)],
    )

    required = next(p for p in catalog[0].props if p.name == "required")
    assert required.varies is False


def test_a_field_that_differs_across_instances_is_a_real_prop():
    catalog = build_catalog(
        [_family(["a", "b"])],
        [_member("a", placeholder="Email"), _member("b", placeholder="Telefono")],
    )

    placeholder = next(p for p in catalog[0].props if p.name == "placeholder")
    assert placeholder.varies is True


def test_style_fields_never_become_props():
    """Colour and typography belong to the design-token document, not to a
    component's interface."""
    catalog = build_catalog(
        [_family(["a"])], [_member("a", background_color="#ff0000", color="#fff")]
    )

    assert "background_color" not in [p.name for p in catalog[0].props]


# --- variants ---

def test_members_differing_only_by_a_modifier_class_are_variants_not_components():
    """common_classes holds what the family shares, so the leftover *is* the
    modifier - a primary/secondary pair is one component with two looks."""
    catalog = build_catalog(
        [_family(["a", "b"], common=("btn",))],
        [_member("a", css_class="btn btn-primary"), _member("b", css_class="btn btn-danger")],
    )

    modifiers = {v.modifiers for v in catalog[0].variants}
    assert modifiers == {("btn-primary",), ("btn-danger",)}


def test_identical_members_collapse_into_one_variant():
    catalog = build_catalog(
        [_family(["a", "b"])], [_member("a"), _member("b")]
    )

    assert len(catalog[0].variants) == 1
    assert catalog[0].variants[0].count == 2


# --- atomic level ---

def test_an_indivisible_tag_is_reported_as_an_atom():
    catalog = build_catalog([_family(["a"], tag="button")], [_member("a")])

    assert catalog[0].atomic_level == "atom"


def test_an_atom_inside_a_form_says_so():
    catalog = build_catalog([_family(["a"], tag="input")], [_member("a", tag="input", form="div > form")])

    assert catalog[0].atomic_level == "atom (in a form)"


def test_an_undeterminable_level_is_omitted_not_guessed():
    """Container nesting isn't captured, so anything that isn't an
    indivisible tag gets no level rather than an invented one."""
    catalog = build_catalog([_family(["a"], tag="div")], [_member("a", tag="div")])

    assert catalog[0].atomic_level == ""


# --- assembly ---

def test_entries_are_ordered_by_how_widely_used_they_are():
    catalog = build_catalog(
        [_family(["a"], component_type="rare"), _family(["b", "c"], component_type="common")],
        [_member("a"), _member("b"), _member("c")],
    )

    assert [entry.component_type for entry in catalog] == ["common", "rare"]


def test_a_family_whose_members_are_missing_from_the_ledger_is_skipped():
    """A family node can outlive the components it clustered - emitting an
    entry with no props or variants would be worse than omitting it."""
    assert build_catalog([_family(["gone"])], []) == []


def test_the_json_document_is_parseable_and_carries_the_same_entries():
    from generators.component_catalog import ComponentCatalogData

    class _Store:
        def get_component_families(self):
            return [_family(["a"], purpose="confirms an action")]

        def get_component_ledger(self):
            return {PAGE: {"a": _member("a")}}

    class _Request:
        graph_store = _Store()
        site = "shop.example"

    payload = json.loads(ComponentCatalogData().generate(_Request()))

    assert payload["components"][0]["name"] == "Button"
    assert payload["components"][0]["purpose"] == "confirms an action"


def test_the_markdown_document_says_which_states_it_cannot_show():
    from generators.component_catalog import ComponentCatalogDocument

    class _Store:
        def get_component_families(self):
            return [_family(["a"])]

        def get_component_ledger(self):
            return {PAGE: {"a": _member("a")}}

    class _Request:
        graph_store = _Store()
        site = "shop.example"

    text = ComponentCatalogDocument().generate(_Request())

    assert "hover" in text and "at rest" in text


def test_instances_are_counted_from_members_the_ledger_actually_has():
    """A family can name a component the ledger no longer holds. Reporting
    the family's own count while describing fewer members is the kind of
    quiet inconsistency that makes a reader distrust the document."""
    catalog = build_catalog(
        [_family(["a", "b", "vanished"])],
        [_member("a"), _member("b")],
    )

    assert catalog[0].member_count == 2
    assert sum(v.count for v in catalog[0].variants) == 2


def test_used_on_lists_only_pages_whose_members_resolved():
    family = ComponentFamily(
        tag="button", component_type="button", common_classes=("btn",),
        member_paths=((PAGE, "a"), ("shop/cart", "gone")), purpose="",
    )

    catalog = build_catalog([family], [_member("a")])

    assert catalog[0].used_on == (PAGE,)
