"""Unit tests for the deterministic component classification/grouping helpers -
no LLM, no scraper, pure functions over plain component dicts."""
import json

from src.generators.component_classifier import (
    classify_component_type,
    describe_options,
    find_revealed_options,
    group_choice_sets,
    group_option_families,
    group_steppers,
)


def test_classify_component_type_covers_common_roles():
    assert classify_component_type({"tag": "div", "role": "option"}) == "list/menu option"
    assert classify_component_type({"tag": "input", "role": "combobox"}) == "combobox (searchable dropdown)"
    assert classify_component_type({"tag": "input", "input_type": "checkbox"}) == "checkbox"
    assert classify_component_type({"tag": "div", "role": "radio"}) == "radio button"
    assert classify_component_type({"tag": "button", "role": "switch"}) == "toggle switch"
    assert classify_component_type({"tag": "div", "role": "tab"}) == "tab"
    assert classify_component_type({"tag": "select"}) == "native dropdown (select)"
    assert classify_component_type({"tag": "input", "input_type": "email"}) == "text field (email)"
    assert classify_component_type({"tag": "input"}) == "text field (text)"
    assert classify_component_type({"tag": "button", "input_type": "submit"}) == "submit button"
    assert classify_component_type({"tag": "button"}) == "button"
    assert classify_component_type({"tag": "a"}) == "link"


def test_classify_component_type_flags_pointer_layer_as_custom_control():
    assert classify_component_type({"tag": "div", "discovery_layer": "pointer"}) == (
        "custom control (component-library element, no native tag/role)"
    )


def test_find_revealed_options_returns_only_newly_appeared_option_role_elements():
    before = [{"tag": "button", "text": "Tercera Docena", "path": "button#trigger"}]
    after = before + [
        {"tag": "div", "text": "Mi Gusto", "path": "div#opt1", "role": "option", "selected": True},
        {"tag": "div", "text": "Solo Empanadas", "path": "div#opt2", "role": "option", "selected": False},
        {"tag": "input", "text": "", "path": "input#search", "role": ""},  # not an option role
    ]
    revealed = find_revealed_options(before, after)
    assert revealed == [
        {"text": "Mi Gusto", "selected": True},
        {"text": "Solo Empanadas", "selected": False},
    ]


def test_find_revealed_options_ignores_already_present_options():
    """An option already present before the click (e.g. re-rendered with the
    same path) must not be reported as newly revealed."""
    same = {"tag": "div", "text": "Mi Gusto", "path": "div#opt1", "role": "option"}
    assert find_revealed_options([same], [same]) == []


def test_find_revealed_options_catches_the_hidden_to_visible_toggle_pattern():
    """The other common reveal pattern (a plain hidden/display:none toggle,
    not a React-portal mount): the option was already in the DOM, just
    CSS-hidden - this must count as revealed too, not just a path that's
    genuinely new to the DOM."""
    before = [{"tag": "div", "text": "Small", "path": "div#opt1", "role": "option", "visible": False}]
    after = [{"tag": "div", "text": "Small", "path": "div#opt1", "role": "option", "visible": True}]
    assert find_revealed_options(before, after) == [{"text": "Small", "selected": False}]


def test_find_revealed_options_ignores_already_visible_options_with_no_visibility_change():
    """A component present and already visible in both snapshots (or absent
    a `visible` key in either) must not be reported as newly revealed via
    the became-visible path - only a genuine False -> True transition counts."""
    already_visible = {"tag": "div", "text": "Small", "path": "div#opt1", "role": "option", "visible": True}
    assert find_revealed_options([already_visible], [already_visible]) == []


def test_group_steppers_detects_increment_decrement_pair_with_value():
    components = [
        {"tag": "button", "text": "Restar", "path": "div#stepper > button:nth-of-type(1)"},
        {"tag": "span", "text": "3", "path": "div#stepper > span"},
        {"tag": "button", "text": "Agregar", "path": "div#stepper > button:nth-of-type(2)"},
        # Unrelated sibling elsewhere on the page - must not be swept into the group.
        {"tag": "button", "text": "Otro boton", "path": "div#other > button"},
    ]
    steppers = group_steppers(components)
    assert len(steppers) == 1
    stepper = steppers[0]
    assert stepper["container"] == "div#stepper"
    assert stepper["decrement_path"] == "div#stepper > button:nth-of-type(1)"
    assert stepper["increment_path"] == "div#stepper > button:nth-of-type(2)"
    assert stepper["value_path"] == "div#stepper > span"
    assert stepper["current_value"] == "3"


def test_group_steppers_works_in_spanish_and_english():
    es = group_steppers([
        {"tag": "button", "text": "Restar", "path": "div#a > button:nth-of-type(1)"},
        {"tag": "button", "text": "Agregar", "path": "div#a > button:nth-of-type(2)"},
    ])
    en = group_steppers([
        {"tag": "button", "text": "Decrease", "path": "div#b > button:nth-of-type(1)"},
        {"tag": "button", "text": "Increase", "path": "div#b > button:nth-of-type(2)"},
    ])
    assert len(es) == 1
    assert len(en) == 1
    # Confirms the vocabulary match is literal, not fuzzy - unrecognized words don't match:
    unrecognized = group_steppers([
        {"tag": "button", "text": "Take away", "path": "div#c > button:nth-of-type(1)"},
        {"tag": "button", "text": "Put in", "path": "div#c > button:nth-of-type(2)"},
    ])
    assert unrecognized == []


def test_group_steppers_requires_both_increment_and_decrement_present():
    only_increment = group_steppers([
        {"tag": "button", "text": "Agregar", "path": "div#a > button:nth-of-type(1)"},
        {"tag": "button", "text": "Some other button", "path": "div#a > button:nth-of-type(2)"},
    ])
    assert only_increment == []


def test_group_choice_sets_groups_same_name_radios_and_drops_singletons():
    components = [
        {"tag": "input", "input_type": "radio", "name": "size", "text": "Small", "path": "input#s"},
        {"tag": "input", "input_type": "radio", "name": "size", "text": "Large", "path": "input#l"},
        {"tag": "input", "input_type": "radio", "name": "solo", "text": "Lonely", "path": "input#solo"},
        {"tag": "input", "input_type": "text", "name": "not-a-choice", "text": "", "path": "input#t"},
    ]
    groups = group_choice_sets(components)
    assert set(groups.keys()) == {"size"}
    assert len(groups["size"]) == 2


def test_group_option_families_groups_siblings_under_the_same_parent():
    components = [
        {"tag": "div", "role": "option", "text": "Small", "path": "div#sizeList > div:nth-of-type(1)"},
        {"tag": "div", "role": "option", "text": "Medium", "path": "div#sizeList > div:nth-of-type(2)"},
        {"tag": "div", "role": "option", "text": "Large", "path": "div#sizeList > div:nth-of-type(3)"},
        # A second, unrelated list elsewhere on the page - must not be swept
        # into the same group just for sharing a role.
        {"tag": "div", "role": "menuitem", "text": "Settings", "path": "div#navMenu > div:nth-of-type(1)"},
        {"tag": "div", "role": "menuitem", "text": "Logout", "path": "div#navMenu > div:nth-of-type(2)"},
    ]
    groups = group_option_families(components)
    assert set(groups.keys()) == {"div#sizeList", "div#navMenu"}
    assert len(groups["div#sizeList"]) == 3
    assert len(groups["div#navMenu"]) == 2


def test_group_option_families_drops_singletons():
    """A single role=option element under a parent isn't 'a list' - leave it
    to record_component's normal per-element path."""
    lone = [{"tag": "div", "role": "option", "text": "Only one", "path": "div#x > div"}]
    assert group_option_families(lone) == {}


def test_group_option_families_excludes_tabs():
    """Tabs usually gate materially different content - each stays its own
    component rather than collapsing into one 'list' node like a dropdown's
    choices do."""
    tabs = [
        {"tag": "div", "role": "tab", "text": "Overview", "path": "div#tabs > div:nth-of-type(1)"},
        {"tag": "div", "role": "tab", "text": "Pricing", "path": "div#tabs > div:nth-of-type(2)"},
    ]
    assert group_option_families(tabs) == {}


def test_describe_options_handles_empty_and_unparseable():
    assert describe_options("") is None
    assert describe_options(None) is None
    assert describe_options("not json") is None
    assert describe_options("42") is None  # valid JSON, not a dict


def test_describe_options_classifies_stepper():
    raw = json.dumps({
        "container": "div#stepper", "increment_path": "button#plus", "decrement_path": "button#minus",
        "value_path": "span#val", "current_value": "3",
    })
    result = describe_options(raw)
    assert result == {
        "kind": "stepper", "container": "div#stepper",
        "increment_path": "button#plus", "decrement_path": "button#minus",
        "value_path": "span#val", "current_value": "3",
    }


def test_describe_options_classifies_choice_group():
    raw = json.dumps({
        "group": "size",
        "options": [
            {"path": "input#s", "text": "Small", "selected": True},
            {"path": "input#l", "text": "Large", "selected": False},
        ],
    })
    result = describe_options(raw)
    assert result == {
        "kind": "choice_group", "group": "size",
        "choices": [
            {"path": "input#s", "text": "Small", "selected": True},
            {"path": "input#l", "text": "Large", "selected": False},
        ],
    }


def test_describe_options_classifies_revealed_options():
    raw = json.dumps({"trigger": "button#sizeTrigger", "revealed_options": [{"text": "Small", "selected": False}]})
    result = describe_options(raw)
    assert result == {
        "kind": "revealed_options", "trigger": "button#sizeTrigger",
        "choices": [{"text": "Small", "selected": False}],
    }
