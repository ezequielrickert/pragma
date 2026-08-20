"""Unit tests for utils/short_hash.py - the shared Short hash convention
(docs/adr/0015-master-llms-txt-manifest-contract.md)."""
from utils.short_hash import short_hash


def test_short_hash_is_ten_hex_characters():
    result = short_hash("example.com/checkout")

    assert len(result) == 10
    assert all(c in "0123456789abcdef" for c in result)


def test_short_hash_is_deterministic():
    assert short_hash("GET example.com/api/orders") == short_hash("GET example.com/api/orders")


def test_short_hash_differs_for_different_input():
    assert short_hash("example.com/cart") != short_hash("example.com/checkout")
