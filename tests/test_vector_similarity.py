"""Unit tests for vector_similarity.py."""
from analysis.vector_similarity import cosine_similarity


def test_identical_vectors_are_similarity_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_orthogonal_vectors_are_similarity_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_opposite_vectors_are_similarity_negative_one():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_a_zero_vector_is_similarity_zero_not_a_division_error():
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
