"""Regression coverage for `Frontier.canonicalize_inventory`
(spiders/orchestration/page_visitor/frontier.py) - issue #170.

A component's own `path` is `nth-of-type`-derived, so it can differ
between two same-page snapshots for what is really one physical DOM
instance (sibling structure shifted between rediscovery passes). Before
this fix, every `record_inventory` call persisted a component's live
path verbatim, so a drifted path for an already-known identity minted a
spurious extra `HAS_COMPONENT` edge (`database/ladybug/component.py`'s
`MERGE` is path-keyed) instead of being recognized as the same instance.
"""
from typing import Any, Dict

from spiders.orchestration.page_visitor.frontier import Frontier


def _component(path: str, text: str = "Neurología", form: str = "sidebar-filters") -> Dict[str, Any]:
    return {"tag": "button", "role": "", "name": "", "form": form, "text": text, "path": path}


def test_a_drifted_path_for_an_already_known_identity_collapses_to_the_first_seen_path():
    frontier = Frontier()
    first_pass = frontier.canonicalize_inventory("page-1", [_component("aside > div:nth-of-type(2) > button")])
    second_pass = frontier.canonicalize_inventory("page-1", [_component("aside > div:nth-of-type(5) > button")])

    assert first_pass[0]["path"] == "aside > div:nth-of-type(2) > button"
    # Same identity, different live path - pinned back to the first one.
    assert second_pass[0]["path"] == "aside > div:nth-of-type(2) > button"


def test_a_genuinely_different_identity_gets_its_own_canonical_path():
    frontier = Frontier()
    neurologia = frontier.canonicalize_inventory("page-1", [_component("aside > div:nth-of-type(2) > button")])
    favoritos = frontier.canonicalize_inventory(
        "page-1", [_component("aside > div:nth-of-type(3) > button", text="Filtrar por favoritos")]
    )

    assert neurologia[0]["path"] != favoritos[0]["path"]


def test_canonicalization_is_scoped_per_page_key_not_shared_site_wide():
    frontier = Frontier()
    on_page_one = frontier.canonicalize_inventory("page-1", [_component("path-a")])
    on_page_two = frontier.canonicalize_inventory("page-2", [_component("path-b")])

    assert on_page_one[0]["path"] == "path-a"
    # A second page starts its own canonical-path map - no cross-page pinning.
    assert on_page_two[0]["path"] == "path-b"


def test_the_original_component_dict_is_never_mutated():
    frontier = Frontier()
    live_component = _component("aside > div:nth-of-type(2) > button")
    frontier.canonicalize_inventory("page-1", [live_component])
    frontier.canonicalize_inventory("page-1", [{**live_component, "path": "aside > div:nth-of-type(5) > button"}])

    # The caller's own component dict still carries its live path - only
    # the copy handed to record_inventory gets pinned, since a frontier
    # item still needs its live path to target the real element.
    assert live_component["path"] == "aside > div:nth-of-type(2) > button"
