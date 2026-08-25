"""Regression coverage for PageInteractionStep (issue #240) - the slim
per-page interaction step that replaces PageVisitor's interaction half.
Duck-typed fake crawlers/gates throughout, same convention
tests/test_page_visitor.py and tests/test_mechanical_loop.py already use
instead of a real-browser fixture.
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import PageState
from spiders.orchestration.interaction_tracker import InMemoryInteractionTracker
from spiders.orchestration.page_interaction import PageInteractionStep


def _fillable(path: str, text: str) -> Dict[str, Any]:
    return {
        "tag": "input", "input_type": "text", "text": text, "path": path,
        "role": "", "form": "", "name": "", "visible": True,
    }


def _clickable(path: str, text: str = "", href: str = "") -> Dict[str, Any]:
    component = {
        "tag": "a" if href else "button", "text": text, "path": path,
        "role": "", "form": "", "name": "", "visible": True, "attributes": {},
    }
    if href:
        component["attributes"]["href"] = href
    return component


async def _no_fill_value(component: Dict[str, Any], page_description: str) -> str:
    return f"generated-for-{component['path']}"


class _FakeCrawler:
    """Scripted click()/fill() responses, keyed by the selector passed in -
    duck-typed, same shape as tests/test_page_visitor.py's fixture."""

    def __init__(self, url: str, responses: Dict[str, PageState]) -> None:
        self.url = url
        self.responses = responses
        self.calls: List[str] = []

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        self.calls.append(selector)
        return self.responses[selector]

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
        self.calls.append(selector)
        return self.responses[selector]


def test_repeated_field_shape_reuses_cached_fill_value():
    """Two fields with identical content identity (component_identity) on
    one page only call fill_value_fn once, same as PageVisitor's own
    cache did."""
    url = "http://fixture/page"
    path_a, path_b = "body > input#a", "body > input#b"
    steady = PageState(url=url, components=[_fillable(path_a, "Email"), _fillable(path_b, "Email")])
    crawler = _FakeCrawler(url, {path_a: steady, path_b: steady})
    calls: List[str] = []

    async def counting_fill_value_fn(component: Dict[str, Any], page_description: str) -> str:
        calls.append(component["path"])
        return f"generated-for-{component['path']}"

    step = PageInteractionStep(crawler, InMemoryInteractionTracker(), counting_fill_value_fn)
    state = PageState(url=url, components=[_fillable(path_a, "Email"), _fillable(path_b, "Email")])
    result = asyncio.run(step.interact(url, "s1", state))

    assert sorted(crawler.calls) == sorted([path_a, path_b])
    assert calls == [path_a]  # the second field reused the cached value
    values = {i.path: i.value for i in result.interactions}
    assert values[path_b] == values[path_a]


def test_click_failure_is_recorded_and_the_pass_continues():
    """An interaction whose crawler call raises is recorded as a failed
    ComponentInteraction and the loop moves on - no resync, no circuit
    breaker (both dropped by this ticket's own scope decision)."""
    url = "http://fixture/page"
    ok_path, broken_path = "body > button#ok", "body > button#broken"
    steady = PageState(url=url, components=[_clickable(ok_path), _clickable(broken_path)])

    class _BreaksOnOnePath(_FakeCrawler):
        async def click(self, url: str, session_id: str, selector: str) -> PageState:
            if selector == broken_path:
                raise RuntimeError("element not found")
            return await super().click(url, session_id, selector)

    crawler = _BreaksOnOnePath(url, {ok_path: steady, broken_path: steady})
    step = PageInteractionStep(crawler, InMemoryInteractionTracker(), _no_fill_value)
    state = PageState(url=url, components=[_clickable(ok_path), _clickable(broken_path)])
    result = asyncio.run(step.interact(url, "s1", state))

    outcomes = {i.path: i for i in result.interactions}
    assert outcomes[broken_path].error == "element not found"
    assert outcomes[ok_path].error is None
    assert result.interrupted_by_navigation is False


def test_physical_navigation_ends_the_pass_without_return_to_origin():
    """A click that lands on a different URL is recorded and marks the
    result interrupted - the pass ends there, no history-back/re-discover
    attempt to keep draining the original page (dropped per this ticket's
    scope decision)."""
    url = "http://fixture/page"
    first_path, second_path = "body > a#first", "body > a#second"
    elsewhere = PageState(url="http://fixture/elsewhere", components=[])
    crawler = _FakeCrawler(url, {first_path: elsewhere})
    step = PageInteractionStep(crawler, InMemoryInteractionTracker(), _no_fill_value)
    state = PageState(url=url, components=[_clickable(first_path), _clickable(second_path)])
    result = asyncio.run(step.interact(url, "s1", state))

    assert result.interrupted_by_navigation is True
    assert crawler.calls == [first_path]  # second_path never attempted - the pass already ended


def test_same_url_reveal_extends_the_frontier_with_new_components():
    """A same-URL click that reveals a new component keeps draining,
    including the newly-revealed one."""
    url = "http://fixture/page"
    trigger_path, revealed_path = "body > button#trigger", "body > input#revealed"
    after_reveal = PageState(
        url=url, components=[_clickable(trigger_path), _fillable(revealed_path, "New field")]
    )
    steady = PageState(url=url, components=[_clickable(trigger_path), _fillable(revealed_path, "New field")])
    crawler = _FakeCrawler(url, {trigger_path: after_reveal, revealed_path: steady})
    step = PageInteractionStep(crawler, InMemoryInteractionTracker(), _no_fill_value)
    state = PageState(url=url, components=[_clickable(trigger_path)])
    result = asyncio.run(step.interact(url, "s1", state))

    assert sorted(crawler.calls) == sorted([trigger_path, revealed_path])
    assert result.interrupted_by_navigation is False


@dataclass
class _FakeReuseEntry:
    interacted: bool
    other_locations: List[Tuple[str, str]] = field(default_factory=list)

    def siblings_of(self, location: Tuple[str, str]) -> List[Tuple[str, str]]:
        return self.other_locations


class _FakeReuseIndex:
    def __init__(self, entry_by_path: Dict[str, _FakeReuseEntry]) -> None:
        self._entry_by_path = entry_by_path
        self.skipped: List[Tuple[str, str]] = []

    def lookup(self, page_key: str, component: Dict[str, Any]) -> Optional[_FakeReuseEntry]:
        return self._entry_by_path.get(component["path"])


def test_exact_reuse_already_interacted_skips_without_a_click():
    url = "http://fixture/page"
    path = "body > button#shared"
    reuse_index = _FakeReuseIndex({path: _FakeReuseEntry(interacted=True)})
    crawler = _FakeCrawler(url, {})
    step = PageInteractionStep(
        crawler, InMemoryInteractionTracker(), _no_fill_value, exact_reuse_index=reuse_index
    )
    state = PageState(url=url, components=[_clickable(path)])
    result = asyncio.run(step.interact(url, "s1", state))

    assert crawler.calls == []
    assert reuse_index.skipped == [("fixture/page", path)]
    assert result.interactions == []


class _FakeFamilySampler:
    def __init__(self, gate_open: bool) -> None:
        self.gate_open = gate_open

    def should_interact(self, page_key: str, component: Dict[str, Any]) -> bool:
        return self.gate_open


def test_family_sampler_gate_can_skip_a_component():
    url = "http://fixture/page"
    path = "body > button#gated"
    crawler = _FakeCrawler(url, {})
    step = PageInteractionStep(
        crawler, InMemoryInteractionTracker(), _no_fill_value, family_sampler=_FakeFamilySampler(gate_open=False)
    )
    state = PageState(url=url, components=[_clickable(path)])
    result = asyncio.run(step.interact(url, "s1", state))

    assert crawler.calls == []
    assert result.interactions == []


def test_static_href_to_a_known_destination_is_skipped_without_clicking():
    url = "http://fixture/page"
    path = "body > a#nav"
    crawler = _FakeCrawler(url, {})
    step = PageInteractionStep(
        crawler, InMemoryInteractionTracker(), _no_fill_value,
        is_known_url=lambda target: target == "http://fixture/known",
    )
    state = PageState(url=url, components=[_clickable(path, href="/known")])
    result = asyncio.run(step.interact(url, "s1", state))

    assert crawler.calls == []
    assert result.interactions == []
