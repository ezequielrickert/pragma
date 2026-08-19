"""`Engine`/`StaticEngine`/`DynamicEngine.from_config` all wrap
`graph_store.connect()` in a broad `except Exception` that falls back to
an in-memory store on a genuine backend failure - but a `SiteLockError`
must never take that path: falling back would silently crawl into a
throwaway store instead of failing loudly, exactly defeating the point
of the lock (docs/dev/database/ladybug/site_lock.md). These prove the
`except SiteLockError: raise` guard each of the three carries actually
stops that fallback.
"""
from core import bootstrap  # noqa: F401  (registers agent/graph-store plugins)
import pytest

from core.config import PragmaConfig
from core.dynamic_engine import DynamicEngine
from core.engine import Engine
from core.static_engine import StaticEngine
from database.ladybug.site_lock import SiteLockError
from database.ladybug.store import LadybugGraphStore

SITE = "locked.example"
URL = f"https://{SITE}/"


def _locked_config(tmp_path) -> PragmaConfig:
    return PragmaConfig(
        url=URL,
        agent="mock",
        graph_store="ladybug",
        graph_stores={"ladybug": {"directory": str(tmp_path)}},
        login_enabled=False,
    )


def test_engine_from_config_does_not_fall_back_to_memory_on_a_lock_conflict(tmp_path):
    holder = LadybugGraphStore(SITE, directory=str(tmp_path))
    holder.connect()
    try:
        with pytest.raises(SiteLockError):
            Engine.from_config(_locked_config(tmp_path))
    finally:
        holder.close()


def test_static_engine_from_config_does_not_fall_back_to_memory_on_a_lock_conflict(tmp_path):
    holder = LadybugGraphStore(SITE, directory=str(tmp_path))
    holder.connect()
    try:
        with pytest.raises(SiteLockError):
            StaticEngine.from_config(_locked_config(tmp_path))
    finally:
        holder.close()


def test_dynamic_engine_from_config_does_not_fall_back_to_memory_on_a_lock_conflict(tmp_path):
    holder = LadybugGraphStore(SITE, directory=str(tmp_path))
    holder.connect()
    try:
        with pytest.raises(SiteLockError):
            DynamicEngine.from_config(_locked_config(tmp_path))
    finally:
        holder.close()
