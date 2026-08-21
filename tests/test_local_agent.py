"""Unit tests for agents/local_agent.py::LocalAgent - no coverage
existed for this module before ADR-0033's refactor (ticket #149) widened
_build_payload/_generate_request to operate on a full messages list
rather than always synthesizing a single prompt+system_instruction pair.
requests.post is mocked throughout; no real HTTP call is ever made."""
from unittest.mock import Mock, patch

from agents.local_agent import LocalAgent


def _agent():
    return LocalAgent(base_url="http://fake-local-model/v1/chat/completions", model="test-model")


def _ok_response(content="a reply"):
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    return response


def test_generate_sends_exactly_one_user_turn():
    agent = _agent()
    with patch("agents.local_agent.requests.post", return_value=_ok_response()) as post:
        result = agent.generate("hello")

    assert result == "a reply"
    sent_messages = post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [{"role": "user", "content": "hello"}]


def test_generate_prepends_system_instruction_as_its_own_turn():
    agent = _agent()
    with patch("agents.local_agent.requests.post", return_value=_ok_response()) as post:
        agent.generate("hello", system_instruction="be terse")

    sent_messages = post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hello"},
    ]


def test_converse_sends_every_turn_not_just_the_latest():
    """The gap generate() alone can't close - ADR-0033's whole point."""
    agent = _agent()
    history = [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
        {"role": "user", "content": "second question"},
    ]
    with patch("agents.local_agent.requests.post", return_value=_ok_response()) as post:
        agent.converse(history, system_instruction="guide the user")

    sent_messages = post.call_args.kwargs["json"]["messages"]
    assert sent_messages == [{"role": "system", "content": "guide the user"}] + history


def test_a_400_with_system_instruction_falls_back_to_a_merged_prompt():
    """generate()'s own existing fallback, unchanged by the refactor -
    some local model servers reject a system role outright."""
    agent = _agent()
    error_response = Mock(status_code=400, text="system role not supported")
    with patch("agents.local_agent.requests.post", side_effect=[error_response, _ok_response()]) as post:
        result = agent.generate("hello", system_instruction="be terse")

    assert result == "a reply"
    second_call_messages = post.call_args_list[1].kwargs["json"]["messages"]
    assert second_call_messages == [{"role": "user", "content": "SYSTEM:\nbe terse\n\nUSER:\nhello"}]


def test_max_tokens_is_only_added_when_actually_set():
    agent = _agent()
    with patch("agents.local_agent.requests.post", return_value=_ok_response()) as post:
        agent.generate("hello")

    assert "max_tokens" not in post.call_args.kwargs["json"]
