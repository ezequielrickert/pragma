"""Regression tests for `analysis/exact_reuse_index.py::ExactReuseIndex` -
`pragma dynamic`'s interact-once tracking for a `Component` reused across
pages, issue #140."""
from analysis.exact_reuse_index import ExactReuseIndex

PAGE_A = "shop.example/a"
PAGE_B = "shop.example/b"


def _identity() -> dict:
    return {"tag": "button", "role": "", "name": "", "form": "", "text": "Buy now"}


def _reused_button(page_url: str, path: str, interacted: bool = False) -> dict:
    return {"id": "canonical-1", "page_url": page_url, "path": path, "interacted": interacted, **_identity()}


def test_lookup_finds_a_component_rendered_on_two_or_more_pages():
    components = [_reused_button(PAGE_A, "#buy"), _reused_button(PAGE_B, "#buy2")]
    index = ExactReuseIndex(components)

    entry = index.lookup(PAGE_A, _identity())

    assert entry is not None
    assert entry.component_id == "canonical-1"
    assert set(entry.locations) == {(PAGE_A, "#buy"), (PAGE_B, "#buy2")}


def test_lookup_returns_none_for_a_component_rendered_on_only_one_page():
    components = [_reused_button(PAGE_A, "#buy")]
    index = ExactReuseIndex(components)

    assert index.lookup(PAGE_A, _identity()) is None


def test_lookup_returns_none_for_an_unrelated_component():
    components = [_reused_button(PAGE_A, "#buy"), _reused_button(PAGE_B, "#buy2")]
    index = ExactReuseIndex(components)

    assert index.lookup(PAGE_A, {"tag": "a", "role": "", "name": "", "form": "", "text": "Home"}) is None


def test_interacted_starts_true_when_any_ledger_member_already_shows_it():
    components = [_reused_button(PAGE_A, "#buy", interacted=True), _reused_button(PAGE_B, "#buy2")]
    index = ExactReuseIndex(components)

    entry = index.lookup(PAGE_A, _identity())

    assert entry.interacted is True


def test_interacted_starts_false_when_no_ledger_member_has_interacted_yet():
    components = [_reused_button(PAGE_A, "#buy"), _reused_button(PAGE_B, "#buy2")]
    index = ExactReuseIndex(components)

    entry = index.lookup(PAGE_A, _identity())

    assert entry.interacted is False


def test_siblings_of_excludes_the_given_location():
    components = [
        _reused_button(PAGE_A, "#buy"), _reused_button(PAGE_B, "#buy2"), _reused_button("shop.example/c", "#buy3"),
    ]
    index = ExactReuseIndex(components)
    entry = index.lookup(PAGE_A, _identity())

    assert entry.siblings_of((PAGE_A, "#buy")) == [(PAGE_B, "#buy2"), ("shop.example/c", "#buy3")]


def test_setting_interacted_is_visible_through_every_location_lookup():
    # Every location's lookup resolves to the *same* entry object -
    # flipping `interacted` at one location must be visible from another,
    # since they all describe one canonical Component row.
    components = [_reused_button(PAGE_A, "#buy"), _reused_button(PAGE_B, "#buy2")]
    index = ExactReuseIndex(components)
    entry = index.lookup(PAGE_A, _identity())

    entry.interacted = True

    assert index.lookup(PAGE_B, _identity()).interacted is True
