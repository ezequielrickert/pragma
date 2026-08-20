"""Unit tests for generators/custom_elements.py - the CEM serialization
of component_catalog.py's pure inference, no store needed."""
import json

from core.documents import DocumentRequest
from core.interfaces import ComponentFamily
from generators.custom_elements import CustomElementsDocument, build_custom_elements_document

PAGE = "shop/"


def _member(path, css_class="btn", background_color="", **facts):
    row = {
        "page_url": PAGE, "path": path, "tag": "button", "text": "Comprar",
        "css_class": css_class, "background_color": background_color, "label": "", "placeholder": "",
        "name": "", "href": "", "form": "", "required": False, "disabled": False,
        "options": ([], ""),
    }
    row.update(facts)
    return row


def _family(paths, tag="button", component_type="button", common=("btn",), purpose=""):
    return ComponentFamily(
        tag=tag, component_type=component_type, common_classes=tuple(common),
        member_paths=tuple((PAGE, path) for path in paths), purpose=purpose,
    )


class _Store:
    def __init__(self, families, members, regions=None, color_tokens=None):
        self._families = families
        self._members = members
        self._regions = regions or {}
        self._color_tokens = color_tokens or {}

    def get_component_families(self):
        return self._families

    def get_component_ledger(self):
        return {PAGE: {member["path"]: member for member in self._members}}

    def get_component_regions(self):
        return self._regions

    def get_state_styles(self):
        return []


def _request(store):
    return DocumentRequest(graph_store=store, site="shop.example", agent=None)


def _document(store):
    return build_custom_elements_document(_request(store))


def test_a_plain_html_tag_is_not_claimed_as_a_custom_element():
    document = _document(_Store([_family(["a"], tag="button")], [_member("a")]))

    declaration = document["modules"][0]["declarations"][0]

    assert declaration["customElement"] is False
    assert "tagName" not in declaration


def test_a_hyphenated_tag_is_reported_as_a_real_custom_element():
    document = _document(_Store([_family(["a"], tag="my-button")], [_member("a", tag="my-button")]))

    declaration = document["modules"][0]["declarations"][0]

    assert declaration["customElement"] is True
    assert declaration["tagName"] == "my-button"


def test_the_module_path_says_it_is_observed_not_a_real_file():
    document = _document(_Store([_family(["a"])], [_member("a")]))

    assert document["modules"][0]["path"] == "observed/Button"


def test_variants_become_x_observed_variants_with_deterministic_screen_ids():
    document = _document(_Store(
        [_family(["a", "b"], common=("btn",))],
        [_member("a", css_class="btn btn-primary"), _member("b", css_class="btn btn-danger")],
    ))

    variants = document["modules"][0]["declarations"][0]["x-observed-variants"]

    assert len(variants) == 2
    assert all(v["screens"][0].startswith("SCR-") for v in variants)
    assert {v["attributes"]["class"] for v in variants} == {"btn-primary", "btn-danger"}


def test_screen_ids_are_deterministic_across_two_builds():
    store = _Store([_family(["a"])], [_member("a")])

    first = _document(store)["modules"][0]["declarations"][0]["x-observed-variants"][0]["screens"]
    second = _document(store)["modules"][0]["declarations"][0]["x-observed-variants"][0]["screens"]

    assert first == second


def test_triggers_and_evidence_are_reserved_not_invented():
    document = _document(_Store([_family(["a"])], [_member("a")]))

    variant = document["modules"][0]["declarations"][0]["x-observed-variants"][0]
    assert variant["triggers"] == []
    assert variant["evidence"] == []


def test_x_region_cites_a_screen_when_one_exists():
    document = _document(_Store([_family(["a"])], [_member("a")], regions={PAGE: {"a": "main"}}))

    region = document["modules"][0]["declarations"][0]["x-region"]

    assert region["screen_id"].startswith("SCR-")
    assert region["landmark_path"] is None
    assert region["aria_role"] is None


def test_x_region_is_absent_without_any_screen():
    """No screen at all (an empty catalog entry never happens, but a
    used_on-less one shouldn't fabricate a screen_id)."""
    from generators.custom_elements import _x_region
    from generators.component_catalog import CatalogEntry

    entry = CatalogEntry(
        name="Ghost", tag="div", component_type="div", purpose="", atomic_level="",
        member_count=0, used_on=(), props=(), variants=(), states_observed=(),
    )

    assert _x_region(entry) is None


def test_x_tokens_cites_a_dtcg_alias_not_a_copied_value():
    """A variant's background_color that matches a real design token gets
    cited by reference - a reader follows the alias into tokens.json
    rather than trusting a second copy of the hex code."""
    document = _document(_Store(
        [_family(["a"])],
        [_member("a", background_color="rgb(45, 119, 55)")],
    ))

    tokens = document["modules"][0]["declarations"][0]["x-tokens"]

    assert tokens["color"] == ["{core.color.surface-1}"]
    assert tokens["spacing"] == []


def test_x_tokens_color_is_absent_when_no_variant_matches_a_real_token():
    document = _document(_Store([_family(["a"])], [_member("a", background_color="")]))

    tokens = document["modules"][0]["declarations"][0]["x-tokens"]

    assert "color" not in tokens


def test_the_document_validates_and_generate_returns_source_and_view():
    outputs = CustomElementsDocument().outputs(_request(_Store([_family(["a"])], [_member("a")])))

    assert [o.filename for o in outputs] == ["custom-elements", "catalog"]
    assert [(o.kind, o.extension) for o in outputs] == [("source", "json"), ("view", "md")]
    json.loads(outputs[0].content)  # already schema-validated inside generate(); just confirm parseable


def test_the_view_reports_component_names_and_variant_screens():
    outputs = CustomElementsDocument().outputs(_request(_Store([_family(["a"])], [_member("a")])))

    view = outputs[1].content

    assert "## Button" in view
    assert "at rest" in view
