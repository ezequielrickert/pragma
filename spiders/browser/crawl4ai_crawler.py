"""crawl4ai-backed page discovery: navigate, run extraction, return PageState.
Details: docs/dev/spiders/browser/crawl4ai_crawler.md#module
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, MemoryAdaptiveDispatcher
from crawl4ai.async_configs import CacheMode

from core.interfaces import PageState
from ..content.network_filter import filter_meaningful_requests
from ..content.page_extraction import (
    extract_pseudo_styles,
    run_accessibility_audit,
    run_extraction,
    walk_tab_order,
)
from .debug_log import CrawlDebugLog
from .dom_settle import _is_navigation_context_error, _wait_for_new_content
from .target_load_throttle import TargetLoadThrottle

# Hands a click/fill's own success/failure back to Python.
# Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_action_mark
_ACTION_MARK = "window.__pragma_last_action__"

# Resource types safe to drop when Crawl4AICrawler.block_images is enabled.
# Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_blocked_resource_types
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


@dataclass
class Crawl4AICrawlerConfig:
    """Every tuning knob `Crawl4AICrawler` accepts, bundled into one object.
    Details: docs/dev/spiders/browser/crawl4ai_crawler.md#crawl4aicrawlerconfig
    """

    headless: bool = True
    wait_seconds: float = 2.0
    interaction_wait_seconds: Optional[float] = None
    debug_log: Optional[CrawlDebugLog] = None
    page_timeout_seconds: float = 15.0
    prefetch: bool = False
    block_images: bool = False
    # Viewport the browser renders at. The crawl default is small on purpose
    # (less render cost per navigation); the measurement pass overrides it
    # with something a person would actually use.
    # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#viewport
    viewport_width: int = 800
    viewport_height: int = 600
    # Run axe-core after each navigation. Off during the crawl: it costs a
    # second per page and its contrast results are wrong with images blocked.
    # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#audit_accessibility
    audit_accessibility: bool = False
    interaction_timeout_seconds: Optional[float] = None
    # Cap on the polite delay grown between navigations when the target
    # server itself is slowing down. `None` disables backoff (and the
    # circuit breaker below) entirely.
    # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#backoff_ceiling_seconds
    backoff_ceiling_seconds: Optional[float] = 20.0
    # How long every worker pauses once the circuit breaker trips (a
    # navigation >= _SEVERE_SLOWDOWN_MULTIPLIER times the crawl's fastest).
    # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#circuit_breaker_cooldown_seconds
    circuit_breaker_cooldown_seconds: float = 10.0


class Crawl4AICrawler:
    """Owns one crawl4ai `AsyncWebCrawler` for the lifetime of an `async with` block.
    Details: docs/dev/spiders/browser/crawl4ai_crawler.md#crawl4aicrawler
    """

    def __init__(self, config: Optional[Crawl4AICrawlerConfig] = None) -> None:
        config = config or Crawl4AICrawlerConfig()
        self.headless = config.headless
        self.interaction_wait_seconds = (
            config.wait_seconds
            if config.interaction_wait_seconds is None
            else config.interaction_wait_seconds
        )
        self.wait_seconds = config.wait_seconds
        self.debug_log = config.debug_log
        self.page_timeout_seconds = config.page_timeout_seconds
        self.prefetch = config.prefetch
        self.block_images = config.block_images
        self.viewport_width = config.viewport_width
        self.viewport_height = config.viewport_height
        self.audit_accessibility = config.audit_accessibility
        self.interaction_timeout_seconds = config.interaction_timeout_seconds
        # Adaptive pacing/circuit-breaker against a straining target server -
        # a separate small class (not inline here) since it has its own,
        # unrelated reason to change from everything else in this file.
        # Details: docs/dev/spiders/browser/target_load_throttle.md#module
        self._throttle = TargetLoadThrottle(
            config.backoff_ceiling_seconds, config.circuit_breaker_cooldown_seconds
        )
        self._crawler: Optional[AsyncWebCrawler] = None
        # session_id -> extraction dict, populated by whichever hook last ran.
        self._stash: Dict[str, Dict[str, Any]] = {}

    async def __aenter__(self) -> "Crawl4AICrawler":
        # light_mode/memory_saving_mode disable background browser features
        # (not layout/CSS - unlike text_mode, which this project deliberately
        # never sets, since discover_components.js needs real computed styles
        # and layout for its pointer-cursor/visibility detection) and a
        # smaller viewport cuts render cost per navigation.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#__aenter__-browserconfig
        browser_config = BrowserConfig(
            headless=self.headless,
            light_mode=True,
            memory_saving_mode=True,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
        )
        self._crawler = AsyncWebCrawler(config=browser_config)
        # Hooks must be registered before __aenter__() is awaited below.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#__aenter__-hook-order
        strategy = self._crawler.crawler_strategy
        strategy.set_hook("before_retrieve_html", self._before_retrieve_html)
        strategy.set_hook("on_execution_ended", self._on_execution_ended)
        # Always registered - on_page_context_created also folds in logging.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#__aenter__-single-slot-hooks
        strategy.set_hook("on_page_context_created", self._on_page_context_created)
        if self.debug_log:
            strategy.set_hook(
                "on_browser_created", self._log_only_hook("on_browser_created")
            )
            strategy.set_hook(
                "on_user_agent_updated", self._log_only_hook("on_user_agent_updated")
            )
            strategy.set_hook(
                "on_execution_started", self._log_only_hook("on_execution_started")
            )
            strategy.set_hook("before_goto", self._log_only_hook("before_goto"))
            strategy.set_hook("after_goto", self._log_only_hook("after_goto"))
            strategy.set_hook(
                "before_return_html", self._log_only_hook("before_return_html")
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

    def _log_only_hook(self, hook_name: str):
        """Build a hook callback that only logs to `self.debug_log`.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_log_only_hook
        """

        def hook(*args, **kwargs):
            # Plain sync callable - crawl4ai's execute_hook calls either way.
            self.debug_log.log_hook_from_raw(hook_name, args, kwargs)
            return args[0] if args else None

        return hook

    async def _on_page_context_created(self, page, context, config, **kwargs):
        """Installs block_images's route handler; fires on every `arun()` call.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_on_page_context_created
        """
        if self.block_images and not getattr(
            page, "_pragma_image_block_installed", False
        ):
            await page.route("**/*", self._maybe_abort_media_request)
            page._pragma_image_block_installed = True
        if self.interaction_timeout_seconds is not None:
            # Changes Playwright's own no-explicit-timeout fallback.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_on_page_context_created-timeout
            page.set_default_timeout(self.interaction_timeout_seconds * 1000)
        if self.debug_log:
            self.debug_log.log_hook_from_raw(
                "on_page_context_created",
                (page,),
                {"context": context, "config": config, **kwargs},
            )
        return page

    async def _maybe_abort_media_request(self, route) -> None:
        if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def _retry_empty_extraction(self, page, data: Dict[str, Any]) -> Dict[str, Any]:
        """Look again when discovery found nothing on a page that clearly has something.

        Zero components *and* zero links on a page with a real DOM is
        almost never true - it is the settle-wait having returned on an
        intermediate render, the same failure `_STABLE_HOLD_SECONDS`
        exists for, on an app whose plateau outlasts that window.
        Confirmed live on empanad.app: `before_retrieve_html` logged 0
        components against 21,891 characters of HTML, and the whole crawl
        produced one page and nothing else.

        Args:
            page: the live page, still open.
            data: whatever `run_extraction` just returned.

        Returns:
            The retried extraction when it found more, otherwise `data`
            unchanged - a page that genuinely has no controls and no links
            (a plain text page) stays empty rather than being retried
            forever. Exactly one extra attempt, so the worst case is one
            more settle-wait on such a page.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_retry_empty_extraction
        """
        if data.get("components") or data.get("links"):
            return data

        await _wait_for_new_content(page, self.wait_seconds)
        retried = await run_extraction(page)
        found = len(retried.get("components") or []) + len(retried.get("links") or [])
        if self.debug_log:
            self.debug_log.log_hook("empty_extraction_retry", found_on_retry=found)
        return retried if found else data

    async def _before_retrieve_html(self, page, context, config, **kwargs):
        """Discovery point for a plain navigation pass (no `js_code` this call).
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_before_retrieve_html
        """
        await _wait_for_new_content(page, self.wait_seconds)
        session_id = config.session_id or "default"
        data = await run_extraction(page)
        data = await self._retry_empty_extraction(page, data)
        if self.audit_accessibility:
            data["accessibility_violations"] = await run_accessibility_audit(page)
            data["pseudo_styles"] = await extract_pseudo_styles(page)
            # Last, because it moves focus around the page - anything read
            # after it would see a page in a state the crawl put it in.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#audit_accessibility
            data["tab_order"] = await walk_tab_order(page)
        self._stash[session_id] = data
        if self.debug_log:
            self.debug_log.log_hook(
                "before_retrieve_html",
                url=page.url,
                session_id=session_id,
                components=len(data["components"]),
                links=len(data["links"]),
                title=data.get("title", ""),
            )
        return page

    async def _on_execution_ended(self, page, context, config, result, **kwargs):
        """Discovery point right after `config.js_code` runs; resolves action success.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_on_execution_ended
        """
        session_id = config.session_id or "default"
        await _wait_for_new_content(page, self.interaction_wait_seconds)
        try:
            data = await run_extraction(page)
        except Exception as exc:
            if not _is_navigation_context_error(exc):
                raise
            # Belt-and-suspenders: give a genuine navigation one more chance to settle.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_on_execution_ended-navigation-retry
            try:
                await page.wait_for_load_state("load", timeout=10000)
            except Exception:
                pass
            data = await run_extraction(page)
        try:
            marked = await page.evaluate(
                f"() => {{ const r = {_ACTION_MARK}; {_ACTION_MARK} = undefined; return r; }}"
            )
        except Exception as exc:
            marked = None if _is_navigation_context_error(exc) else False
        if isinstance(marked, dict):
            action_result = marked
        elif marked is False:
            # Evaluate failed for a reason other than a torn-down context.
            action_result = {
                "success": False,
                "error": "could not read back action result",
            }
        else:
            # Marker never set - fall back to crawl4ai's own execution result.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_on_execution_ended-fallback
            exec_success = bool(result) and result.get("success", False)
            action_result = (
                {"success": True, "navigated": True}
                if exec_success
                else {
                    "success": False,
                    "error": (result or {}).get("error", "js_code did not run"),
                }
            )
        data["action_result"] = action_result
        self._stash[session_id] = data
        if self.debug_log:
            self.debug_log.log_hook(
                "on_execution_ended",
                url=page.url,
                session_id=session_id,
                success=action_result.get("success"),
                navigated=action_result.get("navigated", False),
                error=action_result.get("error", ""),
                components=len(data["components"]),
            )
        return page

    async def discover_page(
        self, url: str, session_id: Optional[str] = None
    ) -> PageState:
        """Navigate to `url` and return its `PageState`; no interaction.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#discover_page
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
            # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#discover_page-network-capture
            capture_network_requests=True,
            page_timeout=int(self.page_timeout_seconds * 1000),
            prefetch=self.prefetch,
        )
        await self._throttle.wait_before_navigation()
        start = asyncio.get_running_loop().time()
        result = await self._crawler.arun(url=url, config=config)
        self._throttle.record_navigation(asyncio.get_running_loop().time() - start)
        if not result.success:
            raise RuntimeError(
                f"crawl4ai navigation failed for {url!r}: {result.error_message}"
            )

        data = self._stash.pop(session_id, {})
        page_state = self._page_state_from_result(result, url, data)
        # The requested url, not page_state.url - see _save_markdown for why.
        self._save_markdown(url, result)
        return page_state

    @staticmethod
    def _resolved_url(result, requested_url: str) -> str:
        """`result.url` is always the requested URL; use `redirected_url` instead.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_resolved_url
        """
        return getattr(result, "redirected_url", None) or result.url or requested_url

    def _page_state_from_result(self, result, requested_url: str, data: Dict[str, Any]) -> PageState:
        """Assemble a `PageState` from one `arun()` result plus its stashed
        extraction dict - shared by `discover_page`, `_interact`, and
        `discover_pages_many` rather than repeated per call site.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_page_state_from_result
        """
        return PageState(
            url=self._resolved_url(result, requested_url),
            title=data.get("title", ""),
            metadata=data.get("metadata", {}),
            components=data.get("components", []),
            links=data.get("links", []),
            description=data.get("description", ""),
            text_content=data.get("text_content", []),
            network_requests=filter_meaningful_requests(getattr(result, "network_requests", None) or []),
            accessibility_violations=data.get("accessibility_violations", []),
            pseudo_styles=data.get("pseudo_styles", []),
            tab_order=data.get("tab_order", []),
        )

    async def discover_pages_many(self, urls: List[str]) -> List[Tuple[str, Optional[PageState]]]:
        """Navigate to every url in `urls` concurrently via crawl4ai's own
        `arun_many()`/`MemoryAdaptiveDispatcher`, instead of this crawler's
        own per-navigation throttle loop.

        Built for `measurement_pass.py`'s shape - many independent,
        already-known URLs, no interaction, no session reuse across calls -
        which is exactly what `arun_many()` is designed for (`discover_page`/
        `_interact`'s single-URL, session-reusing shape is not: crawl4ai has
        no hook to run more `arun()` calls against a URL's session before
        moving to the next one, so that loop stays on `TargetLoadThrottle`).
        Each url gets its own `session_id` (itself) so `_before_retrieve_html`
        stashes into a distinct key per page instead of colliding on
        "default" - same reasoning as `discover_page`'s own default.

        Returns one `(url, PageState)` per successful page, and `(url, None)`
        for a page that failed to load - the batch's own contract, not
        `discover_page`'s raise-on-failure one: a single bad page costs a
        result, not the whole pass.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#discover_pages_many
        """
        if self._crawler is None:
            raise RuntimeError(
                "Crawl4AICrawler must be used as an async context manager"
            )
        if not urls:
            return []
        configs = [
            CrawlerRunConfig(
                session_id=url,
                # A config with no url_matcher matches every URL - without
                # this, arun_many()'s dispatcher binds every concurrent task
                # to configs[0] (confirmed live: two distinct URLs both
                # resolved to the first config's session_id, silently
                # colliding in self._stash and losing one page's extraction
                # entirely). `target=url` captures this iteration's url by
                # value, not the loop variable by reference.
                # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#discover_pages_many-url_matcher
                url_matcher=lambda candidate, target=url: candidate == target,
                cache_mode=CacheMode.BYPASS,
                wait_for="css:body",
                capture_network_requests=True,
                page_timeout=int(self.page_timeout_seconds * 1000),
                prefetch=self.prefetch,
            )
            for url in urls
        ]
        results = await self._crawler.arun_many(
            urls=urls, config=configs, dispatcher=MemoryAdaptiveDispatcher()
        )
        # Keyed by url, not positionally - result.url is always the
        # requested url regardless of arun_many()'s own internal ordering.
        results_by_url = {result.url: result for result in results}

        pages: List[Tuple[str, Optional[PageState]]] = []
        for url in urls:
            result = results_by_url.get(url)
            if result is None or not result.success:
                pages.append((url, None))
                continue
            data = self._stash.pop(url, {})
            pages.append((url, self._page_state_from_result(result, url, data)))
            self._save_markdown(url, result)
        return pages

    def _save_markdown(self, session_id: str, result) -> None:
        """Save crawl4ai's markdown conversion of the page, if debug logging is on.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_save_markdown
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
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_interact
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
            # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_interact-network-capture
            capture_network_requests=True,
            page_timeout=int(self.page_timeout_seconds * 1000),
            prefetch=self.prefetch,
        )
        result = await self._crawler.arun(url=url, config=config)

        # result.success can be False for reasons unrelated to our own action.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler.md#_interact-success-signal
        data = self._stash.pop(session_id, {})
        action_result = data.get("action_result")
        action_succeeded = bool(action_result and action_result.get("success"))

        if not result.success and not action_succeeded:
            raise RuntimeError(
                f"crawl4ai interaction failed for {url!r}: {result.error_message}"
            )
        if not action_succeeded:
            error = (action_result or {}).get("error", "no action result captured")
            raise RuntimeError(f"interaction failed on {url!r}: {error}")

        page_state = self._page_state_from_result(result, url, data)
        self._save_markdown(
            url, result
        )  # the requested url, not page_state.url - see discover_page()
        return page_state

    async def resync(self, url: str, session_id: str) -> PageState:
        """Re-run discovery against the current live DOM; no action, no navigation.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#resync
        """
        js_code = f"{_ACTION_MARK} = {{success: true}};"
        return await self._interact(url, session_id, js_code)

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        """Click `selector` within the session and return the new `PageState`.
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#click
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
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#fill
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
        Details: docs/dev/spiders/browser/crawl4ai_crawler.md#close_session
        """
        if self._crawler is None:
            raise RuntimeError(
                "Crawl4AICrawler must be used as an async context manager"
            )
        await self._crawler.crawler_strategy.kill_session(session_id)
