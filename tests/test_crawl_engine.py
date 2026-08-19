"""Regression tests for `pragma crawl`'s own entry point
(core/crawl_engine.py): proves the static -> cluster -> dynamic chain
runs in order, stops at whichever phase fails first without running the
rest, and never touches `pragma docs`. Fakes every phase engine (via
monkeypatch on the names `crawl_engine.py` itself imports) rather than
running a real crawl - CrawlEngine's own job is the sequencing/stop-on-
failure logic, not anything a real browser would exercise differently.
"""
import asyncio

import pytest

from core.config import PragmaConfig
from core.crawl_engine import CrawlEngine


class _FakePhase:
    """Records that it ran (and with what), in `calls` - shared across
    every fake phase in one test so call order is directly observable."""

    def __init__(self, name, calls, fail=False):
        self.name = name
        self.calls = calls
        self.fail = fail

    def _record_and_maybe_fail(self, arg):
        self.calls.append((self.name, arg))
        if self.fail:
            raise RuntimeError(f"{self.name} exploded")
        return f"{self.name}-result"


class _FakeStaticEngine(_FakePhase):
    async def run(self, url):
        return self._record_and_maybe_fail(url)


class _FakeClusterEngine(_FakePhase):
    def run(self):
        return self._record_and_maybe_fail(None)


class _FakeDynamicEngine(_FakePhase):
    async def run(self, url):
        return self._record_and_maybe_fail(url)


def _wire_fakes(monkeypatch, calls, fail_phase=None):
    monkeypatch.setattr(
        "core.crawl_engine.StaticEngine.from_config",
        staticmethod(lambda config: _FakeStaticEngine("static", calls, fail=fail_phase == "static")),
    )
    monkeypatch.setattr(
        "core.crawl_engine.ClusterEngine.from_config",
        staticmethod(lambda config, site: _FakeClusterEngine("cluster", calls, fail=fail_phase == "cluster")),
    )
    monkeypatch.setattr(
        "core.crawl_engine.DynamicEngine.from_config",
        staticmethod(lambda config: _FakeDynamicEngine("dynamic", calls, fail=fail_phase == "dynamic")),
    )


def test_crawl_runs_all_three_phases_in_order(monkeypatch):
    calls = []
    _wire_fakes(monkeypatch, calls)

    config = PragmaConfig(url="https://shop.example/")
    result = asyncio.run(CrawlEngine.from_config(config).run(config.url))

    assert [name for name, _ in calls] == ["static", "cluster", "dynamic"]
    assert result.succeeded
    assert result.failed_phase is None
    assert result.static == "static-result"
    assert result.cluster == "cluster-result"
    assert result.dynamic == "dynamic-result"


def test_crawl_stops_at_static_and_never_runs_cluster_or_dynamic(monkeypatch):
    calls = []
    _wire_fakes(monkeypatch, calls, fail_phase="static")

    config = PragmaConfig(url="https://shop.example/")
    result = asyncio.run(CrawlEngine.from_config(config).run(config.url))

    assert [name for name, _ in calls] == ["static"]
    assert not result.succeeded
    assert result.failed_phase == "static"
    assert "exploded" in result.error
    assert result.static is None
    assert result.cluster is None
    assert result.dynamic is None


def test_crawl_stops_at_cluster_but_keeps_statics_result(monkeypatch):
    calls = []
    _wire_fakes(monkeypatch, calls, fail_phase="cluster")

    config = PragmaConfig(url="https://shop.example/")
    result = asyncio.run(CrawlEngine.from_config(config).run(config.url))

    assert [name for name, _ in calls] == ["static", "cluster"]
    assert result.failed_phase == "cluster"
    assert result.static == "static-result"
    assert result.cluster is None
    assert result.dynamic is None


def test_crawl_stops_at_dynamic_but_keeps_earlier_results(monkeypatch):
    calls = []
    _wire_fakes(monkeypatch, calls, fail_phase="dynamic")

    config = PragmaConfig(url="https://shop.example/")
    result = asyncio.run(CrawlEngine.from_config(config).run(config.url))

    assert [name for name, _ in calls] == ["static", "cluster", "dynamic"]
    assert result.failed_phase == "dynamic"
    assert result.static == "static-result"
    assert result.cluster == "cluster-result"
    assert result.dynamic is None


def test_crawl_engine_never_imports_docs():
    """`pragma crawl` never auto-chains `pragma docs` - that stays a
    fully separate, explicit invocation. Proven the cheapest possible
    way: the orchestrator's own module has no reference to it at all."""
    import core.crawl_engine as module

    assert not hasattr(module, "DocsEngine")


@pytest.mark.parametrize("fail_phase", ["static", "cluster", "dynamic"])
def test_crawl_engine_derives_site_from_the_url(monkeypatch, fail_phase):
    calls = []
    _wire_fakes(monkeypatch, calls, fail_phase=fail_phase)

    config = PragmaConfig(url="https://shop.example/catalog")
    result = asyncio.run(CrawlEngine.from_config(config).run(config.url))

    assert result.site == "shop.example"
