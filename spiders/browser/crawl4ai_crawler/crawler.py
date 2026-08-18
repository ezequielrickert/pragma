"""crawl4ai-backed page discovery: navigate, run extraction, return PageState.
Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#module
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import CacheMode

from core.interfaces import PageState
from ..target_load_throttle import TargetLoadThrottle
from .config import Crawl4AICrawlerConfig
from .hooks import _ACTION_MARK, HookHandlers
from .page_state import build_page_state
from .quiet_logger import QuietCaptureLogger
from .session_recycle_gate import SessionRecycleGate


class Crawl4AICrawler:
    """Owns one crawl4ai `AsyncWebCrawler` for the lifetime of an `async with` block.
    Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#crawl4aicrawler
    """

    def __init__(self, config: Optional[Crawl4AICrawlerConfig] = None) -> None:
        config = config or Crawl4AICrawlerConfig()
        self.headless = config.headless
        self.debug_log = config.debug_log
        self.page_timeout_seconds = config.page_timeout_seconds
        self.navigation_watchdog_seconds = config.navigation_watchdog_seconds
        self.session_cleanup_timeout_seconds = config.session_cleanup_timeout_seconds
        self.prefetch = config.prefetch
        self.viewport_width = config.viewport_width
        self.viewport_height = config.viewport_height
        # Adaptive pacing/circuit-breaker against a straining target server -
        # a separate small class (not inline here) since it has its own,
        # unrelated reason to change from everything else in this file.
        # Details: docs/dev/spiders/browser/target_load_throttle.md#module
        self._throttle = TargetLoadThrottle(
            config.backoff_ceiling_seconds, config.circuit_breaker_cooldown_seconds
        )
        # Keeps close_session's own context-teardown risk from racing a
        # concurrent worker's in-flight arun() call - see the class's own
        # docstring. Details: docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md#module
        self._session_gate = SessionRecycleGate()
        # Every crawl4ai hook callback plus the stash they read/write -
        # composed, not inlined here. Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#module
        self._hooks = HookHandlers(config)
        self._crawler: Optional[AsyncWebCrawler] = None

    async def __aenter__(self) -> "Crawl4AICrawler":
        # light_mode/memory_saving_mode disable background browser features
        # (not layout/CSS - unlike text_mode, which this project deliberately
        # never sets, since discover_components.js needs real computed styles
        # and layout for its pointer-cursor/visibility detection) and a
        # smaller viewport cuts render cost per navigation.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#__aenter__-browserconfig
        browser_config = BrowserConfig(
            headless=self.headless,
            light_mode=True,
            memory_saving_mode=True,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
        )
        # Own logger, not crawl4ai's default AsyncLogger - drops crawl4ai's
        # own noisy CAPTURE-tag warning without silencing anything else.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#__aenter__-quiet-logger
        self._crawler = AsyncWebCrawler(
            config=browser_config,
            logger=QuietCaptureLogger(verbose=browser_config.verbose),
        )
        # Hooks must be registered before __aenter__() is awaited below.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#__aenter__-hook-order
        strategy = self._crawler.crawler_strategy
        strategy.set_hook("before_retrieve_html", self._hooks.before_retrieve_html)
        strategy.set_hook("on_execution_ended", self._hooks.on_execution_ended)
        # Always registered - on_page_context_created also folds in logging.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#__aenter__-single-slot-hooks
        strategy.set_hook("on_page_context_created", self._hooks.on_page_context_created)
        if self.debug_log:
            strategy.set_hook(
                "on_browser_created", self._hooks.log_only_hook("on_browser_created")
            )
            strategy.set_hook(
                "on_user_agent_updated", self._hooks.log_only_hook("on_user_agent_updated")
            )
            strategy.set_hook(
                "on_execution_started", self._hooks.log_only_hook("on_execution_started")
            )
            strategy.set_hook("before_goto", self._hooks.log_only_hook("before_goto"))
            strategy.set_hook("after_goto", self._hooks.log_only_hook("after_goto"))
            strategy.set_hook(
                "before_return_html", self._hooks.log_only_hook("before_return_html")
            )
        await self._crawler.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._crawler is not None:
            await self._crawler.__aexit__(exc_type, exc, tb)
            self._crawler = None

    @property
    def target_slowdown_ratio(self) -> float:
        """How many times slower the most recent navigation was than the
        fastest one seen this crawl - read by `MechanicalCrawler` to taper
        its own worker count. Details: docs/dev/spiders/browser/target_load_throttle.md#target_slowdown_ratio
        """
        return self._throttle.target_slowdown_ratio

    async def discover_page(
        self, url: str, session_id: Optional[str] = None
    ) -> PageState:
        """Navigate to `url` and return its `PageState`; no interaction.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#discover_page
        """
        if self._crawler is None:
            raise RuntimeError(
                "Crawl4AICrawler must be used as an async context manager"
            )
        session_id = session_id or url
        config = CrawlerRunConfig(
            session_id=session_id,
            cache_mode=CacheMode.BYPASS,
            wait_for="css:body",
            # A page's own load fires the API calls a SPA needs to render at
            # all - not attributable to any one component, but part of the
            # contract all the same.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#discover_page-network-capture
            capture_network_requests=True,
            page_timeout=int(self.page_timeout_seconds * 1000),
            prefetch=self.prefetch,
        )
        await self._throttle.wait_before_navigation()
        start = asyncio.get_running_loop().time()
        result = await self._run_with_watchdog(url, session_id, config)
        self._throttle.record_navigation(asyncio.get_running_loop().time() - start)
        if not result.success:
            raise RuntimeError(
                f"crawl4ai navigation failed for {url!r}: {result.error_message}"
            )

        data = self._hooks.pop(session_id)
        page_state = build_page_state(result, url, data)
        # The requested url, not page_state.url - see _save_markdown for why.
        self._save_markdown(url, result)
        return page_state

    async def _run_with_watchdog(self, url: str, session_id: str, config: CrawlerRunConfig):
        """`self._crawler.arun(...)`, bounded by `navigation_watchdog_seconds` -
        an outer backstop independent of `page_timeout_seconds`, which only
        bounds crawl4ai's own internal navigation clock once a navigation has
        actually started. Shared by `discover_page()` and `_interact()` - both
        go through the identical `arun()` call, and both are equally exposed
        to whatever this guards against.

        Prints a breadcrumb before the call - crawl4ai's own [FETCH]/[SCRAPE]/
        [COMPLETE] lines only print *after* each phase finishes, so a genuine
        hang otherwise leaves no trace of which URL a worker was even
        attempting; confirmed live on austral.edu.ar, where a 12+ minute
        deadlock left nothing to distinguish "which page" from the console
        alone.

        On timeout, best-effort closes `session_id`
        (`_force_close_wedged_session`) before raising - not a full fix (this
        codebase doesn't control crawl4ai's own internals), just an attempt
        to stop this worker's *next* call from inheriting whatever internal
        state caused this one to wedge.

        Holds `_session_gate`'s reader role for the call's duration - see
        `docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md`
        for why a concurrent `close_session` must never tear the shared
        browser context down while this is still in flight.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#_run_with_watchdog
        """
        print(f"[arun] {session_id} -> {url}")
        try:
            async with self._session_gate.reader():
                return await asyncio.wait_for(
                    self._crawler.arun(url=url, config=config), timeout=self.navigation_watchdog_seconds
                )
        except asyncio.TimeoutError as exc:
            await self._force_close_wedged_session(session_id)
            raise RuntimeError(
                f"navigation watchdog: {url!r} did not complete within "
                f"{self.navigation_watchdog_seconds:.0f}s - crawl4ai/Playwright is stuck "
                "somewhere page_timeout_seconds alone doesn't reach (a lock, a hung "
                "subprocess call, etc.), not just a slow page."
            ) from exc

    async def _force_close_wedged_session(self, session_id: str) -> None:
        """Best-effort session cleanup after a watchdog timeout, swallowed -
        a cleanup attempt that's itself stuck on whatever wedged the
        original call must never mask the real error. `close_session` is
        self-bounded (see its own docstring), so no separate `wait_for`
        wrapper is needed here.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#_force_close_wedged_session
        """
        try:
            await self.close_session(session_id)
        except Exception as exc:
            print(f"Warning: could not close wedged session {session_id!r} after watchdog timeout: {exc}")

    def _save_markdown(self, session_id: str, result) -> None:
        """Save crawl4ai's markdown conversion of the page, if debug logging is on.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#_save_markdown
        """
        if not self.debug_log:
            return
        markdown = getattr(result, "markdown", None)
        if not markdown:
            return
        try:
            text = getattr(markdown, "raw_markdown", None) or str(markdown)
            self.debug_log.save_page_markdown(session_id, text)
        except Exception as exc:
            print(f"Warning: could not save debug markdown for {session_id!r}: {exc}")

    async def _interact(self, url: str, session_id: str, js_code: str) -> PageState:
        """Run `js_code` against the existing session (no navigation); raises on failure.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#_interact
        """
        if self._crawler is None:
            raise RuntimeError(
                "Crawl4AICrawler must be used as an async context manager"
            )
        config = CrawlerRunConfig(
            session_id=session_id,
            cache_mode=CacheMode.BYPASS,
            js_only=True,
            js_code=js_code,
            # Scoped to this arun() call only - see doc for why not discover_page().
            # Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#_interact-network-capture
            capture_network_requests=True,
            page_timeout=int(self.page_timeout_seconds * 1000),
            prefetch=self.prefetch,
        )
        result = await self._run_with_watchdog(url, session_id, config)

        # result.success can be False for reasons unrelated to our own action.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#_interact-success-signal
        data = self._hooks.pop(session_id)
        action_result = data.get("action_result")
        action_succeeded = bool(action_result and action_result.get("success"))

        if not result.success and not action_succeeded:
            raise RuntimeError(
                f"crawl4ai interaction failed for {url!r}: {result.error_message}"
            )
        if not action_succeeded:
            error = (action_result or {}).get("error", "no action result captured")
            raise RuntimeError(f"interaction failed on {url!r}: {error}")

        page_state = build_page_state(result, url, data)
        self._save_markdown(
            url, result
        )  # the requested url, not page_state.url - see discover_page()
        return page_state

    async def resync(self, url: str, session_id: str) -> PageState:
        """Re-run discovery against the current live DOM; no action, no navigation.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#resync
        """
        js_code = f"{_ACTION_MARK} = {{success: true}};"
        return await self._interact(url, session_id, js_code)

    async def go_back(self, url: str, session_id: str) -> PageState:
        """Step the session's browser history back one entry and return the
        resulting PageState - unlike `discover_page`, never issues a fresh
        navigation of its own: `history.back()` lets the browser reuse
        whatever it already has for that entry (bfcache, or at minimum the
        ordinary HTTP cache), the same way a person clicking a browser's own
        Back button would, rather than re-requesting the target server for a
        page this session was just rendering a moment ago.

        Goes through `_interact`, not `discover_page` - no separate
        `TargetLoadThrottle` navigation is recorded for it, consistent with
        every other in-session action (`click`/`fill`/`resync`); a `go_back`
        that does end up costing a real request is still far cheaper than a
        full navigation; deliberately not routed through the throttle at all.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#go_back
        """
        js_code = f"""
        (() => {{
            try {{
                history.back();
                {_ACTION_MARK} = {{success: true}};
            }} catch (e) {{
                {_ACTION_MARK} = {{success: false, error: String(e)}};
            }}
        }})();
        """
        return await self._interact(url, session_id, js_code)

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        """Click `selector` within the session and return the new `PageState`.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#click
        """
        sel = json.dumps(selector)
        js_code = f"""
        (() => {{
            try {{
                const el = document.querySelector({sel});
                if (!el) {{ {_ACTION_MARK} = {{success: false, error: 'element not found: ' + {sel}}}; return; }}
                el.click();
                {_ACTION_MARK} = {{success: true}};
            }} catch (e) {{
                {_ACTION_MARK} = {{success: false, error: String(e)}};
            }}
        }})();
        """
        return await self._interact(url, session_id, js_code)

    async def fill(
        self, url: str, session_id: str, selector: str, value: str
    ) -> PageState:
        """Type `value` into `selector` within the session and return the new `PageState`.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#fill
        """
        sel = json.dumps(selector)
        val = json.dumps(value)
        js_code = f"""
        (() => {{
            try {{
                const el = document.querySelector({sel});
                if (!el) {{ {_ACTION_MARK} = {{success: false, error: 'element not found: ' + {sel}}}; return; }}
                const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype
                    : el.tagName === 'SELECT' ? window.HTMLSelectElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value') && Object.getOwnPropertyDescriptor(proto, 'value').set;
                if (setter) {{ setter.call(el, {val}); }} else {{ el.value = {val}; }}
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                {_ACTION_MARK} = {{success: true}};
            }} catch (e) {{
                {_ACTION_MARK} = {{success: false, error: String(e)}};
            }}
        }})();
        """
        return await self._interact(url, session_id, js_code)

    async def close_session(self, session_id: str) -> None:
        """Release the Playwright page/context crawl4ai opened for `session_id`.
        Bounded by `session_cleanup_timeout_seconds` - `kill_session` is
        crawl4ai's own session/browser-management internals, exactly the
        class of code `_run_with_watchdog` already guards `arun()` against.
        Confirmed live on austral.edu.ar as a second, distinct deadlock site
        from the `arun()` one: `MechanicalCrawler._recycle_session_if_due`
        calls this every `session_recycle_after` visits, and an unguarded
        hang here blocked its calling worker forever with no recovery,
        invisible to `navigation_watchdog_seconds` (which only wraps
        `discover_page`/`_interact`'s own `arun()` calls, never this).
        Bounding it here, at the one definition both `_recycle_session_if_due`
        and `_force_close_wedged_session` call through, covers both callers
        at once rather than wrapping each separately.

        Also holds `_session_gate`'s writer role for the call's duration -
        `kill_session` can tear down the *shared* browser context (not just
        this session's own page) if crawl4ai judges this the context's
        last active page, so it must never run concurrently with another
        worker's in-flight `arun()` call. See
        `docs/dev/spiders/browser/crawl4ai_crawler/session_recycle_gate.md`.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/crawler.md#close_session
        """
        if self._crawler is None:
            raise RuntimeError(
                "Crawl4AICrawler must be used as an async context manager"
            )
        try:
            async with self._session_gate.writer(self.navigation_watchdog_seconds):
                await asyncio.wait_for(
                    self._crawler.crawler_strategy.kill_session(session_id),
                    timeout=self.session_cleanup_timeout_seconds,
                )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                f"close_session watchdog: {session_id!r} did not close within "
                f"{self.session_cleanup_timeout_seconds:.0f}s"
            ) from exc
