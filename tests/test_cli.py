"""Argument-parsing tests for src/cli.py - pure argparse, no Engine/network
involved (this project has no existing cli.py test file to follow a precedent
from, so these are intentionally minimal: just confirm the new flags parse to
what the rest of the codebase expects)."""
from src.cli import parse_args, parse_login_args


def test_storage_state_flag_defaults_to_none():
    args = parse_args(["https://example.com"])
    assert args.storage_state_path is None


def test_storage_state_flag_parses():
    args = parse_args(["https://example.com", "--storage-state", "my_session.json"])
    assert args.storage_state_path == "my_session.json"


def test_login_args_require_a_url_and_default_the_storage_state_path():
    args = parse_login_args(["https://example.com/login"])
    assert args.url == "https://example.com/login"
    assert args.storage_state_path == "storage_state.json"


def test_login_args_accept_a_custom_storage_state_path():
    args = parse_login_args(["https://example.com/login", "--storage-state", "custom.json"])
    assert args.storage_state_path == "custom.json"
