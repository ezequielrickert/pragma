"""One-hot/multi-hot encoding into a fixed-size bucket, by deterministic
hash - shared by `leaf_feature_vector.py` and `tailwind_semantic_classes.py`
(issue #168 pulled this out of both; before it, each module carried its own
identical copy). `hashlib.sha1`, never Python's built-in `hash()` -
process-randomized by `PYTHONHASHSEED`, not reproducible across runs. See
`docs/dev/generators/leaf-feature-vector-design.md`'s "Why hashing" section
for the tradeoff this buys (fixed dimensionality across every crawled site)
against exact per-run vocabulary indexing.

Details: docs/dev/analysis/deterministic_hashing.md#module
"""
from __future__ import annotations

import hashlib
from typing import Iterable, List


def _bucket(value: str, bucket_count: int) -> int:
    digest = hashlib.sha1((value or "").encode()).digest()
    return int.from_bytes(digest[:4], "big") % bucket_count


def hash_one_hot(value: str, bucket_count: int) -> List[float]:
    """One field's value, hashed into one of `bucket_count` slots - an
    empty string hashes like any other value, so "this field is absent"
    collides into one shared bucket rather than being dropped: lacking a
    value is itself a signal, not noise.
    Details: docs/dev/analysis/deterministic_hashing.md#hash_one_hot
    """
    vector = [0.0] * bucket_count
    vector[_bucket(value, bucket_count)] = 1.0
    return vector


def hash_multi_hot(values: Iterable[str], bucket_count: int) -> List[float]:
    """A *set* of values, each hashed and OR'd into one binary vector -
    membership, independent of order or repeats, is what determines this
    slice.
    Details: docs/dev/analysis/deterministic_hashing.md#hash_multi_hot
    """
    vector = [0.0] * bucket_count
    for value in values:
        if value:
            vector[_bucket(value, bucket_count)] = 1.0
    return vector
