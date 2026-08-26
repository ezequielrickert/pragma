"""Unit tests for screen_narrator.narrate_screens - mirrors
tests/test_component_family_narrator.py's structure for the analogous
Screen narration step."""
from typing import List, Optional, Tuple

from core.interfaces import Agent, SemanticScreen
from generators.screen_narrator import (
    SCREEN_SYSTEM_INSTRUCTION,
    _parse_response,
    build_page_context,
    narrate_screens,
    screen_signature,
)


class RecordingAgent(Agent):
    """Fake agent that records every call, same pattern as
    tests/test_component_family_narrator.py's RecordingAgent."""

    def __init__(self, response: str = "NAME: Checkout\nPURPOSE: Confirms and pays for the order.") -> None:
        self.calls: List[Tuple[str, Optional[str]]] = []
        self._response = response

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.calls.append((prompt, system_instruction))
        return self._response


class RaisingAgent(Agent):
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        raise RuntimeError("boom")


def _screen(page_url="shop.example/checkout", route_pattern="shop.example/checkout") -> SemanticScreen:
    return SemanticScreen(page_url=page_url, route_pattern=route_pattern)


def test_parse_response_reads_both_labeled_lines():
    name, purpose = _parse_response("NAME: Checkout\nPURPOSE: Confirms and pays for the order.")
    assert name == "Checkout"
    assert purpose == "Confirms and pays for the order."


def test_parse_response_is_case_insensitive_and_tolerates_stray_whitespace():
    name, purpose = _parse_response("  name:   Cart  \n  purpose:   Reviews items before paying.  ")
    assert name == "Cart"
    assert purpose == "Reviews items before paying."


def test_parse_response_returns_blank_pair_for_a_malformed_response():
    assert _parse_response("Sure, here's a screen name for you!") == ("", "")


def test_build_page_context_merges_titles_and_descriptions():
    context = build_page_context({"/a": "Title A"}, {"/a": "Desc A", "/b": "Desc B"})
    assert context == {"/a": ("Title A", "Desc A"), "/b": ("", "Desc B")}


def test_narrate_screens_calls_agent_with_title_and_description():
    agent = RecordingAgent()
    screen = _screen()

    result = narrate_screens(agent, [screen], {screen.page_url: ("Checkout", "Pay for your order")})

    assert len(agent.calls) == 1
    prompt, system_instruction = agent.calls[0]
    assert system_instruction is SCREEN_SYSTEM_INSTRUCTION
    assert "Checkout" in prompt
    assert "Pay for your order" in prompt
    assert result[0].name == "Checkout"
    assert result[0].purpose == "Confirms and pays for the order."
    # Every other field carried over unchanged.
    assert result[0].page_url == screen.page_url
    assert result[0].route_pattern == screen.route_pattern


def test_narrate_screens_skips_a_screen_with_no_title_or_description():
    agent = RecordingAgent()
    screen = _screen()

    result = narrate_screens(agent, [screen], {})

    assert agent.calls == []
    assert result[0].name == ""
    assert result[0].purpose == ""


def test_narrate_screens_degrades_on_agent_failure_without_aborting():
    agent = RaisingAgent()
    screens = [_screen("shop.example/a"), _screen("shop.example/b")]
    context = {"shop.example/a": ("A", ""), "shop.example/b": ("B", "")}

    result = narrate_screens(agent, screens, context)

    assert len(result) == 2
    assert all(s.name == "" and s.purpose == "" for s in result)


def test_narrate_screens_one_bad_screen_does_not_block_the_next():
    class FlakyAgent(Agent):
        def __init__(self) -> None:
            self.call_count = 0

        def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
            self.call_count += 1
            if self.call_count == 1:
                raise RuntimeError("first screen fails")
            return "NAME: Cart\nPURPOSE: Reviews items before paying."

    agent = FlakyAgent()
    screens = [_screen("shop.example/a"), _screen("shop.example/b")]
    context = {"shop.example/a": ("A", ""), "shop.example/b": ("B", "")}

    result = narrate_screens(agent, screens, context)

    assert result[0].name == ""
    assert result[1].name == "Cart"


def test_an_unchanged_screen_keeps_its_name_and_purpose_without_asking_again():
    screen = _screen()
    agent = _CountingAgent()

    result = narrate_screens(
        agent, [screen], {screen.page_url: ("Checkout", "")},
        known_purposes={screen_signature(screen): ("Checkout", "confirms and pays")},
    )

    assert agent.calls == 0
    assert result[0].name == "Checkout"
    assert result[0].purpose == "confirms and pays"


def test_a_screen_whose_route_pattern_changed_is_narrated_again():
    before = _screen(route_pattern="shop.example/old-shape")
    after = _screen(route_pattern="shop.example/new-shape")
    agent = _CountingAgent()

    result = narrate_screens(
        agent, [after], {after.page_url: ("Checkout", "")},
        known_purposes={screen_signature(before): ("stale name", "stale purpose")},
    )

    assert agent.calls == 1
    assert result[0].name != "stale name"


class _CountingAgent(Agent):
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.calls += 1
        return "NAME: Freshly narrated\nPURPOSE: Freshly narrated purpose."
