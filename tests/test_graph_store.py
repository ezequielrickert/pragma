"""Engine <-> graph-store wiring tests - not storage contract tests.

The contract the store must satisfy (upsert/record/get semantics) lives in
`tests/test_ladybug_observation.py`/`test_ladybug_read_path.py`. What
stays here is specific to how `Engine.from_config` wires a chosen backend
in - `LadybugGraphStore` in-memory mode, since it needs no setup at all.
"""
from typing import Optional

from database.ladybug.store import LadybugGraphStore


class _SpyGraphStore(LadybugGraphStore):
    """Records `reset()` calls without touching disk - exercises
    `Engine.from_config`'s `PragmaConfig.fresh` wiring directly."""

    def __init__(self, site: str, directory: Optional[str] = None) -> None:
        super().__init__(site, directory=None)  # always in-memory, regardless of directory
        self.reset_calls: list = []

    def reset(self) -> None:
        self.reset_calls.append(self.site)
        super().reset()


def test_engine_from_config_resets_when_fresh(tmp_path):
    from core.config import PragmaConfig
    from core.engine import Engine
    from core.registry import GRAPH_STORE_REGISTRY

    GRAPH_STORE_REGISTRY.register("_spy_fresh_test")(_SpyGraphStore)
    # Explicit, like its fresh=False sibling below: purging stopped being the
    # default once a cut-short run's Pending pages became resumable progress,
    # so relying on the default here would test whatever that default happens
    # to be rather than the behavior this test is named for.
    config = PragmaConfig(
        url="https://stub.example/page", agent="mock",
        graph_store="_spy_fresh_test", fresh=True, out_dir=str(tmp_path),
    )

    engine = Engine.from_config(config)
    assert isinstance(engine.graph_store, _SpyGraphStore)
    assert engine.graph_store.reset_calls == ["stub.example"]


def test_engine_from_config_skips_reset_when_not_fresh(tmp_path):
    from core.config import PragmaConfig
    from core.engine import Engine
    from core.registry import GRAPH_STORE_REGISTRY

    GRAPH_STORE_REGISTRY.register("_spy_no_fresh_test")(_SpyGraphStore)
    config = PragmaConfig(
        url="https://stub.example/page", agent="mock",
        graph_store="_spy_no_fresh_test", fresh=False, out_dir=str(tmp_path),
    )

    engine = Engine.from_config(config)
    assert engine.graph_store.reset_calls == []
