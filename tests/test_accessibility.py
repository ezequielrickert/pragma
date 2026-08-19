"""Unit tests for the deterministic accessibility audit
(generators/accessibility.py) - pure functions over hand-built ledger rows -
plus get_page_landmarks against the real engine.
"""
from __future__ import annotations

import pytest

from database.ladybug.store import LadybugGraphStore
from generators.accessibility import (
    AccessibilityDocument,
    accessible_name,
    landmark_findings,
    name_findings,
)

PAGE = "https://shop.example/checkout"


@pytest.fixture
def store():
    instance = LadybugGraphStore("shop.example")
    instance.connect()
    try:
        yield instance
    finally:
        instance.close()


def _control(path, component_type="button", text="Comprar", **extra):
    row = {
        "page_url": PAGE, "path": path, "tag": "button", "component_type": component_type,
        "text": text, "label": "", "placeholder": "", "layer": "semantic",
    }
    row.update(extra)
    return row


# --- accessible name ---

def test_visible_text_is_a_name():
    assert accessible_name(_control("b#1", text="Guardar")) == "Guardar"


def test_a_label_association_is_a_name_when_there_is_no_text():
    """An input's innerText is always empty; its name comes from <label>."""
    field = _control("i#1", component_type="text field (text)", text="", label="Email")

    assert accessible_name(field) == "Email"


def test_a_placeholder_is_not_a_name():
    """It disappears on input and is not announced consistently - which is the
    whole point of the placeholder-as-only-label rule."""
    field = _control("i#1", component_type="text field (text)", text="", placeholder="Email")

    assert accessible_name(field) == ""


# --- name rules ---

def test_a_nameless_button_is_a_4_1_2_finding():
    findings = name_findings([_control("b#1", text="")])

    assert len(findings) == 1
    assert findings[0].rule == "missing-accessible-name"
    assert findings[0].criterion.startswith("WCAG 4.1.2")
    assert findings[0].severity == "high"


def test_a_nameless_field_with_a_placeholder_gets_the_specific_rule_only():
    """The fix differs - promote the placeholder versus invent a name - and
    reporting both would double-count one element."""
    findings = name_findings([
        _control("i#1", component_type="text field (text)", text="", placeholder="Email")
    ])

    assert [f.rule for f in findings] == ["placeholder-as-only-label"]


def test_a_named_control_produces_nothing():
    assert name_findings([_control("b#1", text="Pagar")]) == []


def test_a_field_named_only_by_aria_label_is_not_a_finding():
    """aria-label IS a programmatic label; the discovery chain resolves it into
    `text`, so flagging it would be wrong."""
    field = _control("i#1", component_type="text field (text)", text="Buscar en el sitio")

    assert name_findings([field]) == []


def test_the_pointer_catch_all_layer_is_skipped():
    """An unnamed clickable div is a real failure and a decorative wrapper is
    not; the crawl cannot tell them apart, so neither is reported."""
    findings = name_findings([
        _control("div#1", component_type="custom control (component-library element, "
                                        "no native tag/role)", text="", layer="pointer")
    ])

    assert findings == []


def test_a_plain_element_needs_no_name():
    assert name_findings([_control("span#1", component_type="element", text="")]) == []


# --- landmark rules ---

def test_a_page_with_landmarks_but_no_main_is_a_2_4_1_finding():
    findings = landmark_findings({PAGE: {"banner": 1, "navigation": 1}})

    assert [f.rule for f in findings] == ["no-main-landmark"]
    assert findings[0].criterion.startswith("WCAG 2.4.1")


def test_two_banners_on_one_page_are_reported():
    findings = landmark_findings({PAGE: {"main": 1, "banner": 2}})

    assert [f.rule for f in findings] == ["duplicate-unique-landmark"]
    assert "2 separate `banner`" in findings[0].detail


def test_several_navigation_regions_are_correct_markup():
    """navigation is deliberately not in _UNIQUE_LANDMARKS."""
    assert landmark_findings({PAGE: {"main": 1, "navigation": 3}}) == []


def test_a_page_with_no_recorded_ancestry_is_not_judged():
    """"No main region" and "containment was never captured" are different
    claims, and only the page's absence distinguishes them."""
    assert landmark_findings({}) == []


# --- the read this depends on ---

def test_get_page_landmarks_counts_distinct_regions_not_components(store) -> None:
    """Two banners holding three components between them count 2, not 3 - which
    is the number WCAG cares about."""
    store.upsert_page(PAGE, status="Finished")
    store.record_components(PAGE, [
        {"path": "a#1", "tag": "a", "text": "One"},
        {"path": "a#2", "tag": "a", "text": "Two"},
        {"path": "a#3", "tag": "a", "text": "Three"},
    ])
    store.record_component_ancestors(PAGE, [
        {"path": "a#1", "ancestors": [{"path": "header#h1", "tag": "header", "landmark": "banner"}]},
        {"path": "a#2", "ancestors": [{"path": "header#h1", "tag": "header", "landmark": "banner"}]},
        {"path": "a#3", "ancestors": [{"path": "header#h2", "tag": "header", "landmark": "banner"}]},
    ])

    assert store.get_page_landmarks() == {PAGE: {"banner": 2}}


def test_get_page_landmarks_is_empty_without_ancestry(store) -> None:
    store.upsert_page(PAGE, status="Finished")
    store.record_components(PAGE, [{"path": "a#1", "tag": "a", "text": "One"}])

    assert store.get_page_landmarks() == {}


# --- the document ---

class _Store:
    def __init__(self, ledger, landmarks):
        self._ledger = ledger
        self._landmarks = landmarks

    def get_component_ledger(self):
        return self._ledger

    def get_page_landmarks(self):
        return self._landmarks


class _Request:
    def __init__(self, store):
        self.graph_store = store
        self.site = "shop.example"


def test_the_document_always_states_that_it_is_partial():
    """A clean accessibility report that looks complete is worse than none."""
    text = AccessibilityDocument().generate(_Request(_Store({}, {})))

    assert "partial audit, not a conformance check" in text
    assert "does not mean the application is accessible" in text


def test_the_document_reports_findings_with_their_criterion():
    ledger = {PAGE: {"b#1": _control("b#1", text="")}}
    text = AccessibilityDocument().generate(_Request(_Store(ledger, {PAGE: {"banner": 1}})))

    assert "missing-accessible-name" in text
    assert "WCAG 4.1.2" in text
    assert "no-main-landmark" in text


def test_the_document_counts_the_elements_it_skipped():
    """The exclusion is this document's own blind spot, so it belongs in it."""
    ledger = {PAGE: {"div#1": _control("div#1", component_type="custom control", layer="pointer")}}
    text = AccessibilityDocument().generate(_Request(_Store(ledger, {})))

    assert "1 element(s) found only by the `cursor: pointer` catch-all are excluded" in text


def test_no_findings_is_stated_narrowly():
    ledger = {PAGE: {"b#1": _control("b#1", text="Pagar")}}
    text = AccessibilityDocument().generate(_Request(_Store(ledger, {PAGE: {"main": 1}})))

    assert "Read that narrowly" in text
