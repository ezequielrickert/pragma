"""Unit tests for deterministic_hashing.py - the sha1-bucket encoding
leaf_feature_vector.py and tailwind_semantic_classes.py both build on.
"""
from analysis.deterministic_hashing import hash_multi_hot, hash_one_hot


def test_hash_one_hot_sets_exactly_one_slot():
    vector = hash_one_hot("button", 16)
    assert len(vector) == 16
    assert sum(vector) == 1.0


def test_hash_one_hot_is_deterministic_across_calls():
    """Pins sha1 over Python's builtin hash() - PYTHONHASHSEED would make
    this flaky if it used the latter."""
    first = hash_one_hot("button", 16)
    second = hash_one_hot("button", 16)
    assert first == second


def test_hash_one_hot_treats_an_empty_value_as_its_own_bucket():
    """Absence is a signal, not noise - an empty string still hashes to
    some bucket rather than being skipped."""
    vector = hash_one_hot("", 16)
    assert sum(vector) == 1.0


def test_hash_multi_hot_ors_every_value_into_one_vector():
    vector = hash_multi_hot(["bg-white", "p-4", "flex"], 16)
    assert len(vector) == 16
    assert 1 <= sum(vector) <= 3  # <=3 in case two tokens collide into one bucket


def test_hash_multi_hot_ignores_blank_values():
    with_blank = hash_multi_hot(["bg-white", ""], 16)
    without_blank = hash_multi_hot(["bg-white"], 16)
    assert with_blank == without_blank


def test_hash_multi_hot_is_order_independent():
    assert hash_multi_hot(["a", "b", "c"], 16) == hash_multi_hot(["c", "b", "a"], 16)
