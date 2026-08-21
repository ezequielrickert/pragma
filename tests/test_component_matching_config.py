"""Unit tests for component_matching_config.py's YAML-merge loader - same
"never an error, fall back to hardcoded defaults" contract
core/config.py::PragmaConfig follows, exercised against real temp files
rather than mocked I/O.
"""
from pathlib import Path

from analysis.component_matching_config import ComponentMatchingConfig


def test_a_missing_file_returns_every_hardcoded_default():
    config = ComponentMatchingConfig.load("/nonexistent/component_matching.yaml")

    assert config == ComponentMatchingConfig()


def test_the_shipped_default_file_round_trips_to_the_same_hardcoded_values():
    """config/component_matching.yaml documents the same starting values
    the dataclass defaults already carry - this pins that they can't
    silently drift apart."""
    config = ComponentMatchingConfig.load("config/component_matching.yaml")

    assert config == ComponentMatchingConfig()


def test_a_partial_override_only_changes_the_keys_it_names(tmp_path: Path):
    yaml_path = tmp_path / "component_matching.yaml"
    yaml_path.write_text("thresholds:\n  leaf_exact: 0.99\n")

    config = ComponentMatchingConfig.load(str(yaml_path))

    assert config.thresholds.leaf_exact == 0.99
    assert config.thresholds.leaf_family == ComponentMatchingConfig().thresholds.leaf_family
    assert config.leaf_weights == ComponentMatchingConfig().leaf_weights


def test_an_unknown_key_inside_a_known_block_is_silently_ignored(tmp_path: Path):
    yaml_path = tmp_path / "component_matching.yaml"
    yaml_path.write_text("thresholds:\n  leaf_exact: 0.99\n  made_up_setting: 1\n")

    config = ComponentMatchingConfig.load(str(yaml_path))

    assert config.thresholds.leaf_exact == 0.99


def test_an_unknown_top_level_block_is_silently_ignored(tmp_path: Path):
    yaml_path = tmp_path / "component_matching.yaml"
    yaml_path.write_text("made_up_block:\n  x: 1\n")

    config = ComponentMatchingConfig.load(str(yaml_path))

    assert config == ComponentMatchingConfig()


def test_an_empty_file_returns_every_hardcoded_default(tmp_path: Path):
    yaml_path = tmp_path / "component_matching.yaml"
    yaml_path.write_text("")

    config = ComponentMatchingConfig.load(str(yaml_path))

    assert config == ComponentMatchingConfig()
