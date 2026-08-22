"""Unit tests for core/interactive_cli.py - argument parsing and the
config/agent-resolution hand-off to run_interactive_server, which is
mocked throughout so no real server ever starts. --agent mock is
forced in the hand-off tests so they don't depend on whatever real
agent this machine's own pragma.yaml happens to configure."""
from unittest.mock import patch

from agents.mock_agent import MockAgent
from core.interactive_cli import parse_interactive_args, run_interactive_command


def test_parse_interactive_args_defaults_host_and_port():
    args = parse_interactive_args(["example.com"])

    assert args.site == "example.com"
    assert args.host == "127.0.0.1"
    assert args.port == 5050
    assert args.out_dir is None
    assert args.agent is None


def test_parse_interactive_args_accepts_overrides():
    args = parse_interactive_args([
        "example.com", "--host", "0.0.0.0", "--port", "9000", "--out", "custom/dir", "--agent", "mock",
    ])

    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.out_dir == "custom/dir"
    assert args.agent == "mock"


def test_run_interactive_command_resolves_out_dir_and_agent_then_hands_off():
    with patch("core.interactive_cli.run_interactive_server") as run_server:
        run_interactive_command(["example.com", "--out", "custom/dir", "--port", "9000", "--agent", "mock"])

    run_server.assert_called_once()
    args, kwargs = run_server.call_args
    assert args[0] == "custom/dir"
    assert args[1] == "example.com"
    assert isinstance(args[2], MockAgent)
    assert kwargs == {"host": "127.0.0.1", "port": 9000}


def test_run_interactive_command_uses_the_default_out_dir_when_not_overridden():
    with patch("core.interactive_cli.run_interactive_server") as run_server:
        run_interactive_command(["example.com", "--agent", "mock"])

    called_out_dir = run_server.call_args.args[0]
    assert called_out_dir  # PragmaConfig's own default, not asserted to a literal here


def test_run_interactive_command_falls_back_to_mock_when_the_configured_agent_fails_to_init():
    """The exact DocsEngine.from_config pattern - a chat feature nobody
    might even use this run must never crash the whole session."""
    with patch("core.interactive_cli.AGENT_REGISTRY.create", side_effect=[RuntimeError("boom"), MockAgent()]) as create, \
         patch("core.interactive_cli.run_interactive_server") as run_server:
        run_interactive_command(["example.com", "--agent", "definitely-not-a-real-agent"])

    assert create.call_args_list[-1].args[0] == "mock"
    assert isinstance(run_server.call_args.args[2], MockAgent)
