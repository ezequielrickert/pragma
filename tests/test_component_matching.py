"""Unit tests for `spiders.content.component_matching`.
"""
from __future__ import annotations

from spiders.content.component_matching import remap_stale_frontier


def _button(path: str, name: str = "Conectar") -> dict[str, str]:
    return {"tag": "button", "role": "button", "name": name, "form": "", "text": name, "path": path}


def test_remaps_each_same_identity_item_onto_a_distinct_fresh_instance():
    """Three stale "Conectar" buttons from three different professional
    cards must land on three different fresh paths, not all collapse onto
    the first one found (issue #225).
    """
    remaining = [_button("/card[1]/button"), _button("/card[2]/button"), _button("/card[3]/button")]
    fresh = [_button("/card[1]/button[2]"), _button("/card[2]/button[2]"), _button("/card[3]/button[2]")]

    remapped, dropped = remap_stale_frontier(remaining, fresh)

    assert dropped == []
    remapped_paths = [c["path"] for c in remapped]
    assert remapped_paths == [c["path"] for c in fresh]


def test_a_path_kept_as_is_is_not_handed_out_again_as_a_remap_target():
    """The first card's button still resolves under its own path, so it
    must be kept as-is - and that fresh instance must not also be handed
    to the second, genuinely-stale button.
    """
    remaining = [_button("/card[1]/button"), _button("/card[2]/button")]
    fresh = [_button("/card[1]/button"), _button("/card[2]/button[2]")]

    remapped, dropped = remap_stale_frontier(remaining, fresh)

    assert dropped == []
    assert [c["path"] for c in remapped] == ["/card[1]/button", "/card[2]/button[2]"]


def test_excess_same_identity_items_are_dropped_once_the_pool_is_exhausted():
    """More stale items share an identity than the fresh snapshot has
    instances of it - the surplus is dropped and reported, not silently
    doubled up onto an already-claimed path.
    """
    remaining = [_button("/card[1]/button"), _button("/card[2]/button")]
    fresh = [_button("/card[1]/button[2]")]

    remapped, dropped = remap_stale_frontier(remaining, fresh)

    assert [c["path"] for c in remapped] == ["/card[1]/button[2]"]
    assert dropped == ["/card[2]/button"]


def test_distinct_identities_never_share_a_pool():
    remaining = [_button("/card[1]/connect", name="Conectar"), _button("/card[1]/share", name="Compartir")]
    fresh = [_button("/card[1]/connect[2]", name="Conectar"), _button("/card[1]/share[2]", name="Compartir")]

    remapped, dropped = remap_stale_frontier(remaining, fresh)

    assert dropped == []
    assert {c["path"] for c in remapped} == {"/card[1]/connect[2]", "/card[1]/share[2]"}
