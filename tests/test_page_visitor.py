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
