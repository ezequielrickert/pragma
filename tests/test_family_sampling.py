"""Regression tests for `analysis/family_sampling.py::FamilySampler` -
`pragma dynamic`'s mechanism for skipping redundant interaction on
components a `pragma cluster` family already covers."""
from core.data_contracts import ComponentFamily
from analysis.family_sampling import FamilySampler

PAGE = "shop.example"


def _button(text: str) -> dict:
    return {"tag": "button", "role": "", "name": "", "form": "", "text": text, "path": f"#{text}"}


def _family(paths) -> ComponentFamily:
    return ComponentFamily(
        tag="button", component_type="submit button", common_classes=("btn",),
        member_paths=tuple((PAGE, path) for path in paths),
    )


def _components(*texts: str) -> list:
    # `id` mirrors `flat_component_ledger`'s real shape post-#136 - one
    # distinct canonical id per distinct component here, since each of
    # these fixture buttons is a genuinely different Component row, not
    # the same one rendered on several pages.
    return [{"page_url": PAGE, "path": f"#{t}", "id": f"id-{t}", **_button(t)} for t in texts]


def test_should_interact_keeps_the_first_max_samples_members_of_a_family():
    components = _components("a", "b", "c", "d")
    family = _family(["#a", "#b", "#c", "#d"])
    sampler = FamilySampler([family], components, max_samples=2)

    decisions = [sampler.should_interact(PAGE, _button(t)) for t in ("a", "b", "c", "d")]

    assert decisions == [True, True, False, False]
    assert len(sampler.skipped) == 2


def test_should_interact_always_interacts_with_a_component_that_belongs_to_no_family():
    sampler = FamilySampler([], [], max_samples=2)

    assert sampler.should_interact(PAGE, _button("standalone")) is True
    assert sampler.skipped == []


def test_should_interact_matches_by_content_identity_not_stale_path():
    """A family's member_paths carries the path recorded at clustering
    time; a live interact-sweep component can have re-derived a different
    path after a fresh discover_page() reload, but the same tag/role/name/
    form/text identity - matching must survive that churn."""
    components = _components("a", "b", "c")
    family = _family(["#a", "#b", "#c"])
    sampler = FamilySampler([family], components, max_samples=1)

    live_component = {**_button("a"), "path": "#totally-different-live-path"}

    assert sampler.should_interact(PAGE, live_component) is True
    assert sampler.should_interact(PAGE, _button("b")) is False
