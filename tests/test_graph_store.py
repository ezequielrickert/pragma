"""Engine <-> GraphStore wiring tests - not GraphStore contract tests.

The contract every backend must satisfy (upsert/record/get semantics) lives
in `test_graph_store_conformance.py`, run once per registered backend. What
stays here is specific to how `Engine.from_config` wires a chosen backend
in, which only needs one (any) backend to exercise - `InMemoryGraphStore`
because it needs no live server.
"""
from database.memory_graph_store import InMemoryGraphStore


class _SpyGraphStore(InMemoryGraphStore):
    """Records `clear_site` calls without needing a live Neo4j instance -
    exercises `Engine.from_config`'s `PragmaConfig.fresh` wiring directly."""

    def __init__(self) -> None:
        super().__init__()
        self.cleared_sites: list = []

    def clear_site(self, site: str) -> None:
        self.cleared_sites.append(site)
        super().clear_site(site)


def test_engine_from_config_clears_site_when_fresh(tmp_path):
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
    assert engine.graph_store.cleared_sites == ["stub.example"]


def test_engine_from_config_skips_clear_when_not_fresh(tmp_path):
    from core.config import PragmaConfig
    from core.engine import Engine
    from core.registry import GRAPH_STORE_REGISTRY

    GRAPH_STORE_REGISTRY.register("_spy_no_fresh_test")(_SpyGraphStore)
    config = PragmaConfig(
        url="https://stub.example/page", agent="mock",
        graph_store="_spy_no_fresh_test", fresh=False, out_dir=str(tmp_path),
    )

    engine = Engine.from_config(config)
    assert engine.graph_store.cleared_sites == []
