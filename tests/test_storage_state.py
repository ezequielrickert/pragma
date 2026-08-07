"""Tests for optional Playwright storage-state support (login persistence) -
PlaywrightScraper.storage_state_path/_browser_context_kwargs, RestScraper's
drop-in acceptance of the same kwarg, and Engine.from_config wiring."""
from src.scrapers.playwright_scraper import PlaywrightScraper
from src.scrapers.rest_scraper import RestScraper


def test_storage_state_kwargs_empty_by_default():
    """None (the default) must behave exactly as before this feature existed -
    an empty browser context, no storage_state kwarg passed at all."""
    scraper = PlaywrightScraper()
    assert scraper._browser_context_kwargs() == {}


def test_storage_state_kwargs_used_when_file_exists(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.write_text("{}", encoding="utf-8")
    scraper = PlaywrightScraper(storage_state_path=str(state_file))
    assert scraper._browser_context_kwargs() == {"storage_state": str(state_file)}


def test_storage_state_kwargs_missing_file_degrades_gracefully(tmp_path, capsys):
    """A configured-but-not-yet-created path (login was never run) must not
    raise - just fall back to a fresh, logged-out context with a warning."""
    missing_path = str(tmp_path / "does-not-exist.json")
    scraper = PlaywrightScraper(storage_state_path=missing_path)

    kwargs = scraper._browser_context_kwargs()

    assert kwargs == {}
    output = capsys.readouterr().out
    assert "not found" in output
    assert "python3 src/cli.py login" in output


def test_rest_scraper_accepts_storage_state_path_as_a_drop_in_noop():
    """RestScraper must remain a drop-in swap for PlaywrightScraper in pragma.yaml -
    accepting (and ignoring) the same kwargs Engine.from_config always passes."""
    scraper = RestScraper(headless=True, wait_seconds=1.0, storage_state_path="/some/path.json")
    assert scraper is not None  # constructing it at all must not raise


def test_engine_from_config_passes_storage_state_path_to_the_scraper(tmp_path):
    from src.core.config import PragmaConfig
    from src.core.engine import Engine
    from src.core.interfaces import Scraper, PageState
    from src.core.registry import SCRAPER_REGISTRY

    captured = {}

    class _SpyScraper(Scraper):
        def __init__(self, headless=True, wait_seconds=15.0, storage_state_path=None):
            captured["storage_state_path"] = storage_state_path

        def navigate(self, url):
            return PageState(url=url, title="", components=[], links=[])

        def click(self, selector):
            return self.get_state()

        def get_state(self):
            return PageState(url="https://stub", title="")

        def close(self):
            pass

    SCRAPER_REGISTRY.register("_spy_storage_state_test")(_SpyScraper)
    config = PragmaConfig(
        url="https://stub.example/page", scraper="_spy_storage_state_test", agent="mock",
        graph_store="memory", out_dir=str(tmp_path), logs_dir=str(tmp_path),
        progress_logs_dir=str(tmp_path), graph_logs_dir=str(tmp_path),
        storage_state_path="/configured/state.json",
    )

    Engine.from_config(config)

    assert captured["storage_state_path"] == "/configured/state.json"
