"""Regression coverage for PageVisitor's fill-value cache
(src/crawlers/page_visitor.py's `_fill_value_cache`/`_fill_value`).

Every fillable field previously called `fill_value_fn` fresh, even when a
page has two fields with the same shape (same tag/role/name/form/text -
`component_matching.component_identity`). Since `fill_value_fn` is a live
AI call by default (`fill_value_agent.generate_fill_value`), that's a
real, avoidable cost per repeated field. A duck-typed fake crawler drives
`MechanicalCrawler` the same way `tests/test_mechanical_loop.py` does for
scripted failure modes - see that module's own note on why a fake is used
instead of a real-browser fixture here.
"""
import asyncio
from typing import Any, Dict, List

from src.core.interfaces import PageState
from src.crawlers.mechanical_loop import MechanicalCrawler, MechanicalCrawlerConfig


def _fillable(path: str, text: str) -> Dict[str, Any]:
    return {
        "tag": "input", "input_type": "text", "text": text, "path": path,
        "role": "", "form": "", "name": "", "visible": True,
    }


class _FakeTwoIdenticalFieldsCrawler:
    """One page, two `<input>` fields with identical content identity
    (same tag/role/name/form/text) but distinct paths - the shape that
    made every repeated-field fill call `fill_value_fn` again before the
    cache existed."""

    def __init__(self) -> None:
        self.url = "http://fixture/page"
        self.path_a = "body > input#a"
        self.path_b = "body > input#b"
        self.filled: List[str] = []

    async def discover_page(self, url: str, session_id=None) -> PageState:
        return PageState(
            url=self.url,
            components=[
                _fillable(self.path_a, "Email"),
                _fillable(self.path_b, "Email"),
            ],
        )

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        raise AssertionError("fixture has only fillable components")

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        self.filled.append(selector)
        # Steady-state response: nothing revealed, the same two fields remain.
        return PageState(
            url=self.url,
            components=[_fillable(self.path_a, "Email"), _fillable(self.path_b, "Email")],
        )

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("fixture never triggers a resync")


def test_repeated_field_shape_reuses_cached_value_instead_of_recalling_fill_value_fn():
    fake = _FakeTwoIdenticalFieldsCrawler()
    calls: List[str] = []

    async def counting_fill_value_fn(component: Dict[str, Any], page_description: str) -> str:
        calls.append(component["path"])
        return f"generated-for-{component['path']}"

    mech = MechanicalCrawler(
        fake,
        config=MechanicalCrawlerConfig(max_pages=1, fill_value_fn=counting_fill_value_fn),
    )
    results = asyncio.run(mech.crawl_site(fake.url))
    interactions = results[0].interactions

    # Both fields were still filled...
    assert sorted(fake.filled) == sorted([fake.path_a, fake.path_b])
    # ...but the value-generating function only ran once, for the first.
    assert calls == [fake.path_a]

    values = {i.path: i.value for i in interactions}
    assert values[fake.path_a] == "generated-for-" + fake.path_a
    # The second field reused the first one's cached value, not a fresh call.
    assert values[fake.path_b] == values[fake.path_a]


def _clickable(path: str, text: str) -> Dict[str, Any]:
    return {
        "tag": "a", "input_type": "", "text": text, "path": path,
        "role": "", "form": "", "name": "", "visible": True,
    }


class _FakeSuppressedNavigationCrawler:
    """One page whose *first* component would navigate away. With navigation
    suppression on, `click` reports the aborted destination instead of a
    changed URL - the pass must keep going through the rest of the page's
    frontier from the same live session, and queue that destination as a
    page of its own."""

    def __init__(self) -> None:
        self.url = "http://fixture/start"
        self.destination = "http://fixture/elsewhere"
        self.leaves = "body > a#leave"
        self.stays = "body > a#stay"
        self.clicked: List[str] = []
        self.discovered: List[str] = []

    def _components(self) -> List[Dict[str, Any]]:
        return [_clickable(self.leaves, "Leave"), _clickable(self.stays, "Stay")]

    async def discover_page(self, url: str, session_id=None) -> PageState:
        self.discovered.append(url)
        if url == self.destination:
            return PageState(url=self.destination, components=[])
        return PageState(url=self.url, components=self._components())

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        self.clicked.append(selector)
        suppressed = (
            [{"url": self.destination, "method": "GET"}] if selector == self.leaves else []
        )
        # The URL is unchanged either way - that's the whole point of the abort.
        return PageState(url=self.url, components=self._components(), suppressed_navigations=suppressed)

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        raise AssertionError("fixture has no fillable components")

    async def resync(self, url: str, session_id: str) -> PageState:
        raise AssertionError("fixture never triggers a resync")


def test_suppressed_navigation_finishes_the_page_and_queues_the_destination():
    fake = _FakeSuppressedNavigationCrawler()
    mech = MechanicalCrawler(fake, config=MechanicalCrawlerConfig())
    results = asyncio.run(mech.crawl_site(fake.url))

    start = results[0]
    # The pass was not cut short: both components were interacted with in one visit.
    assert fake.clicked == [fake.leaves, fake.stays]
    assert start.interrupted_by_navigation is False
    assert start.suppressed_navigations == [fake.destination]
    # ...and the start page was fetched exactly once, with the destination
    # visited as its own page rather than chased inline.
    assert fake.discovered == [fake.url, fake.destination]
    # The ledger still records where that component leads.
    resulting = {i.path: i.resulting_url for i in start.interactions}
    assert resulting[fake.leaves] == "fixture/elsewhere"
