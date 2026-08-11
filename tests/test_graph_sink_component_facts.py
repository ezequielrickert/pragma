"""Unit tests for graph_sink._component_facts - the pure mapping from one
JS-discovered component dict (discover_components.js's per-element shape)
onto ComponentFacts, exercised directly so a field-name typo on either side
of that boundary fails fast instead of silently writing "" to Neo4j/memory.
"""
from src.core.interfaces import ComponentFacts
from src.crawlers.graph_sink import _component_facts


def test_component_facts_maps_attributes_and_style():
    comp = {
        "tag": "button",
        "text": "Go",
        "placeholder": "",
        "label": "Go",
        "name": "go-button",
        "disabled": False,
        "required": False,
        "form": "form#checkout",
        "attributes": {"id": "go-btn", "class": "btn btn-primary", "href": ""},
        "style": {
            "color": "rgb(255, 255, 255)",
            "background_color": "rgb(0, 100, 200)",
            "font_size": "16px",
            "font_weight": "700",
            "display": "inline-block",
            "position": "static",
        },
    }
    facts = _component_facts(comp)

    assert facts == ComponentFacts(
        css_class="btn btn-primary",
        element_id="go-btn",
        href="",
        placeholder="",
        label="Go",
        name="go-button",
        disabled=False,
        required=False,
        form="form#checkout",
        color="rgb(255, 255, 255)",
        background_color="rgb(0, 100, 200)",
        font_size="16px",
        font_weight="700",
        display="inline-block",
        position="static",
    )


def test_component_facts_defaults_blank_when_attributes_and_style_are_missing():
    # A component dict from a source that predates this field set (or a
    # hand-built test double) must not raise - every fact is just "".
    facts = _component_facts({"tag": "button", "text": "Go"})
    assert facts == ComponentFacts()


def test_component_facts_excludes_live_value_deliberately():
    # `value` is a real key discover_components.js emits, but it's not part
    # of ComponentFacts - a fill's actual value is already captured by
    # record_component_interaction, which is the reliable source (see
    # _component_facts's own docstring for why re-reading .value here would
    # just be a second, possibly-stale copy of the same fact).
    facts = _component_facts({"tag": "input", "value": "typed text"})
    assert not hasattr(facts, "value")
