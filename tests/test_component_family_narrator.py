"""Unit tests for component_family_narrator.narrate_family_purposes."""
from typing import List, Optional, Tuple

from src.core.interfaces import Agent, ComponentFamily
from src.generators.component_family_narrator import (
    PURPOSE_SYSTEM_INSTRUCTION,
    narrate_family_purposes,
)


class RecordingAgent(Agent):
    """Fake agent that records every call, same pattern as
    tests/test_graph_prd_synthesizer.py's RecordingAgent."""

    def __init__(self, response: str = "Confirms or submits an action.") -> None:
        self.calls: List[Tuple[str, Optional[str]]] = []
        self._response = response

    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        self.calls.append((prompt, system_instruction))
        return self._response


class RaisingAgent(Agent):
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        raise RuntimeError("boom")


def _family(paths=(("p1", "a1"), ("p1", "a2"))) -> ComponentFamily:
    return ComponentFamily(tag="button", component_type="button", common_classes=("btn",), member_paths=paths)


def test_narrate_family_purposes_calls_agent_with_member_texts():
    agent = RecordingAgent()
    family = _family()
    member_texts = {("p1", "a1"): "Confirmar", ("p1", "a2"): "Aceptar"}

    result = narrate_family_purposes(agent, [family], member_texts)

    assert len(agent.calls) == 1
    prompt, system_instruction = agent.calls[0]
    assert system_instruction is PURPOSE_SYSTEM_INSTRUCTION
    assert "Confirmar" in prompt
    assert "Aceptar" in prompt
    assert result[0].purpose == "Confirms or submits an action."
    # Every other field carried over unchanged.
    assert result[0].tag == family.tag
    assert result[0].member_paths == family.member_paths


def test_narrate_family_purposes_strips_the_response():
    agent = RecordingAgent(response="  Adjusts quantity.  \n")
    result = narrate_family_purposes(agent, [_family()], {("p1", "a1"): "Sumar", ("p1", "a2"): "Restar"})
    assert result[0].purpose == "Adjusts quantity."


def test_narrate_family_purposes_skips_families_with_no_member_text():
    agent = RecordingAgent()
    family = _family(paths=(("p1", "a1"),))
    result = narrate_family_purposes(agent, [family], {("p1", "a1"): ""})
    assert agent.calls == []
    assert result[0].purpose == ""


def test_narrate_family_purposes_degrades_on_agent_failure_without_aborting():
    agent = RaisingAgent()
    families = [_family(paths=(("p1", "a1"),)), _family(paths=(("p2", "b1"),))]
    member_texts = {("p1", "a1"): "Confirmar", ("p2", "b1"): "Cancelar"}

    result = narrate_family_purposes(agent, families, member_texts)

    assert len(result) == 2
    assert all(f.purpose == "" for f in result)


def test_narrate_family_purposes_one_bad_family_does_not_block_the_next():
    class FlakyAgent(Agent):
        def __init__(self) -> None:
            self.call_count = 0

        def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
            self.call_count += 1
            if self.call_count == 1:
                raise RuntimeError("first family fails")
            return "Cancels the current flow."

    agent = FlakyAgent()
    families = [_family(paths=(("p1", "a1"),)), _family(paths=(("p2", "b1"),))]
    member_texts = {("p1", "a1"): "Confirmar", ("p2", "b1"): "Cancelar"}

    result = narrate_family_purposes(agent, families, member_texts)

    assert result[0].purpose == ""
    assert result[1].purpose == "Cancels the current flow."
