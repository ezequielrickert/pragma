"""Unit tests for core/interactive_cli.py - argument parsing and the
config-resolution/hand-off to run_interactive_server, which is mocked
throughout so no real server ever starts."""
from unittest.mock import patch

from core.interactive_cli import parse_interactive_args, run_interactive_command


def test_parse_interactive_args_defaults_host_and_port():
    args = parse_interactive_args(["example.com"])

    assert args.site == "example.com"
    assert args.host == "127.0.0.1"
    assert args.port == 5050
    assert args.out_dir is None


def test_parse_interactive_args_accepts_overrides():
    args = parse_interactive_args(["example.com", "--host", "0.0.0.0", "--port", "9000", "--out", "custom/dir"])

    assert args.host == "0.0.0.0"
    assert args.port == 9000
    assert args.out_dir == "custom/dir"


def test_run_interactive_command_resolves_out_dir_and_hands_off():
    with patch("core.interactive_cli.run_interactive_server") as run_server:
        run_interactive_command(["example.com", "--out", "custom/dir", "--port", "9000"])

    run_server.assert_called_once_with("custom/dir", "example.com", host="127.0.0.1", port=9000)


def test_run_interactive_command_uses_the_default_out_dir_when_not_overridden():
    with patch("core.interactive_cli.run_interactive_server") as run_server:
        run_interactive_command(["example.com"])

    called_out_dir = run_server.call_args.args[0]
    assert called_out_dir  # PragmaConfig's own default, not asserted to a literal here
