"""Cosine similarity over the plain `list[float]` vectors this package's
matching modules (`leaf_feature_vector.py`, `composite_matching.py`)
produce - a tiny, dependency-free stand-in for what `QUERY_VECTOR_INDEX`
does against a real Kùzu `FLOAT[n]` column once one exists (issue #139).

Details: docs/dev/analysis/vector_similarity.md#module
"""
from __future__ import annotations

import math
from typing import Sequence


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """`0.0` for either zero vector (an all-absent component compared
    against anything) rather than a `ZeroDivisionError` - two vectors
    with nothing in them share no genuine similarity signal to report.
    Details: docs/dev/analysis/vector_similarity.md#cosine_similarity
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)
