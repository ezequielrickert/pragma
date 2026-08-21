"""Tunables for the component-matching pipeline (issue #127) - the leaf
feature-vector block weights `leaf_feature_vector.py` applies and the
leaf/composite thresholds and bucketing slack #132/#133 decided, all in
one place per `docs/dev/generators/matching-threshold-calibration.md`.

Deliberately its own file, `config/component_matching.yaml`, not a block
inside `pragma.yaml`: this map's tunables are a distinct concern from the
general run config, and keeping them apart means a threshold tweak while
calibrating never touches the file that also carries crawl-mode settings.

The merge discipline mirrors `core/config.py::PragmaConfig._apply_yaml` -
a missing file, or a missing/unknown key within it, never raises; it just
falls back to the hardcoded default below. Unlike `PragmaConfig`, this is
three flat, one-level-nested blocks, not ~30 top-level fields, so a small
hand-rolled merge reads more plainly here than reusing that machinery.

Details: docs/dev/analysis/component_matching_config.md#module
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULT_CONFIG_PATH = "config/component_matching.yaml"


@dataclass(frozen=True)
class LeafWeights:
    """Per-block scale applied to a leaf feature vector's slices before
    concatenation (`leaf_feature_vector.py`) - the knob that controls how
    much each block influences the resulting cosine similarity.
    Details: docs/dev/analysis/component_matching_config.md#leafweights
    """

    structural: float = 1.0
    identity_strings: float = 0.8
    css_class: float = 0.6
    style: float = 0.5
    geometry: float = 0.15


@dataclass(frozen=True)
class MatchingThresholds:
    """Where "family" ends and "exact reuse" begins, at both the leaf and
    composite tiers - issue #133's four independent constants.
    Details: docs/dev/analysis/component_matching_config.md#matchingthresholds
    """

    leaf_family: float = 0.55
    leaf_exact: float = 0.92
    composite_family: float = 0.5
    composite_exact: float = 0.9


@dataclass(frozen=True)
class CompositeBucketing:
    """How much two composites' child counts may differ by and still be
    compared - issue #132 step 1's bucketing slack, before any per-child
    work runs.
    Details: docs/dev/analysis/component_matching_config.md#compositebucketing
    """

    child_count_slack: float = 0.5


@dataclass(frozen=True)
class ComponentMatchingConfig:
    """The whole matching pipeline's tunables, loaded once per run and
    passed into whichever stage needs them.
    Details: docs/dev/analysis/component_matching_config.md#componentmatchingconfig
    """

    leaf_weights: LeafWeights = field(default_factory=LeafWeights)
    thresholds: MatchingThresholds = field(default_factory=MatchingThresholds)
    composite_bucketing: CompositeBucketing = field(default_factory=CompositeBucketing)

    @classmethod
    def load(cls, path: str = DEFAULT_CONFIG_PATH) -> "ComponentMatchingConfig":
        """Read `path`, falling back to every hardcoded default above for
        a missing file, a missing block, or a missing/unknown key within
        one - the same "never an error" contract
        `PragmaConfig._apply_yaml` follows.
        Details: docs/dev/analysis/component_matching_config.md#load
        """
        data = _read_yaml(path)
        return cls(
            leaf_weights=_merge_block(LeafWeights, data.get("leaf_weights")),
            thresholds=_merge_block(MatchingThresholds, data.get("thresholds")),
            composite_bucketing=_merge_block(CompositeBucketing, data.get("composite_bucketing")),
        )


def _read_yaml(path: str) -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    return yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}


def _merge_block(block_cls: type, values: Optional[Dict[str, Any]]):
    """One nested block (`LeafWeights`, `MatchingThresholds`,
    `CompositeBucketing`) built from `block_cls`'s own defaults, overridden
    field-by-field by whichever keys `values` actually has - an absent
    block, an absent key, or a key the dataclass doesn't define are all
    silently ignored rather than raising.
    Details: docs/dev/analysis/component_matching_config.md#_merge_block
    """
    valid = {f.name for f in fields(block_cls)}
    overrides = {k: v for k, v in (values or {}).items() if k in valid and v is not None}
    return block_cls(**overrides)
