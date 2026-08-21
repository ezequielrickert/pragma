"""Unit tests for core/interfaces.py::Agent - specifically converse()'s
default behavior (ADR-0033, ticket #149): every existing agent
subclass inherits it without any changes of its own, so what matters
is that the default degrades gracefully rather than erroring."""
import pytest

from core.interfaces import Agent


class _EchoAgent(Agent):
    """A minimal concrete Agent - generate() alone, converse() left as
    the base class's own default, the same shape every real subclass
    that hasn't been given a real history mechanism has today."""

    def generate(self, prompt, system_instruction=None):
        return f"echo: {prompt}"


def test_converse_default_uses_only_the_last_user_turn():
    agent = _EchoAgent()
    messages = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
    ]

    reply = agent.converse(messages)

    assert reply == "echo: second question"


def test_converse_default_passes_system_instruction_through_to_generate():
    class _RecordingAgent(_EchoAgent):
        def generate(self, prompt, system_instruction=None):
            self.seen_system_instruction = system_instruction
            return super().generate(prompt, system_instruction)

    recording = _RecordingAgent()
    recording.converse([{"role": "user", "content": "hi"}], system_instruction="be terse")

    assert recording.seen_system_instruction == "be terse"


def test_converse_default_raises_a_clear_error_with_no_user_turn_at_all():
    """A boundary condition the plain next()-with-no-default this used
    to be would have surfaced as a cryptic StopIteration instead."""
    agent = _EchoAgent()

    with pytest.raises(ValueError, match="at least one message"):
        agent.converse([{"role": "assistant", "content": "only an assistant turn"}])
