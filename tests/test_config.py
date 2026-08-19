"""Regression tests for `core/config.py`'s `mode` field: the surface a
sensitive-site crawl uses to opt into `immutable` (see PragmaConfig.mode).
"""
import pytest

from core.config import PragmaConfig
from core.crawl_cli import parse_crawl_args
from core.dynamic_cli import parse_dynamic_args


def test_mode_defaults_to_stateful():
    assert PragmaConfig().mode == "stateful"


def test_mode_accepts_immutable_via_cli_override():
    config = PragmaConfig.load(cli_overrides={"mode": "immutable"})
    assert config.mode == "immutable"


def test_mode_rejects_an_unrecognized_value():
    with pytest.raises(ValueError, match="stateful"):
        PragmaConfig.load(cli_overrides={"mode": "read-only"})


def test_dynamic_cli_accepts_mode_flag():
    args = parse_dynamic_args(["http://example.com", "--mode", "immutable"])
    assert args.mode == "immutable"


def test_dynamic_cli_rejects_an_unrecognized_mode():
    with pytest.raises(SystemExit):
        parse_dynamic_args(["http://example.com", "--mode", "read-only"])


def test_crawl_cli_accepts_mode_flag():
    args = parse_crawl_args(["http://example.com", "--mode", "immutable"])
    assert args.mode == "immutable"
