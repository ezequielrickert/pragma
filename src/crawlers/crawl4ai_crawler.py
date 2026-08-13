"""crawl4ai-backed page discovery: navigate, run extraction, return PageState.
Details: docs/dev/crawlers/crawl4ai_crawler.md#module
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import CacheMode

from ..core.interfaces import PageState
from .debug_log import CrawlDebugLog
from .network_filter import filter_meaningful_requests
from .page_extraction import (
    extract_pseudo_styles,
    run_accessibility_audit,
    run_extraction,
    walk_tab_order,
)
from .target_load_throttle import TargetLoadThrottle

# Hands a click/fill's own success/failure back to Python.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_action_mark
_ACTION_MARK = "window.__pragma_last_action__"

# Resource types safe to drop when Crawl4AICrawler.block_images is enabled.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_blocked_resource_types
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}

# Below this many DOM elements, "no components and no links" is a
# believable description of the page rather than a sign we looked too
# early. Well under any real application screen, well above an error page.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_retry_empty_extraction
_EMPTY_EXTRACTION_MIN_NODES = 50

# _wait_for_new_content's poll step.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_adaptive_wait_step_seconds
_ADAPTIVE_WAIT_STEP_SECONDS = 0.1

# How long the DOM-change signal must hold steady, after it first differs
# from where it started, before _wait_for_new_content treats it as settled.
# Live-verified against a real crawl of empanad.app (2026-08-11): after
# clicking into the order flow, the signal changes once at ~0.24s (a false,
# intermediate render step - 10 chars of body text, clearly a loading
# state) and holds there for only ~0.13s before the real destination
# content appears at ~0.49s (445 chars of body text, the actual 3
# components). A single 0.1s poll step of "stability" (this function's
# first version) is shorter than that ~0.13s plateau, so it returned on the
# fake intermediate step - this margin is chosen to comfortably outlast it.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_stable_hold_seconds
_STABLE_HOLD_SECONDS = 0.4

# Cheap proxy for "did the DOM change", polled by _wait_for_new_content instead
# of the full DISCOVER_COMPONENTS_JS pass (which forces a getComputedStyle()
# per element and is far too expensive to run ~20x per interaction just to
# check whether anything changed). Node count alone missed real changes on
# sites where an interaction toggles a class (active filter chip) or updates
# text (a results count) without adding/removing any element - live-verified
# against mapadeprofesionales.com, where 35 of 39 interactions always slept
# the full ceiling instead of returning early. Text length and total class
# count are just as cheap (one pass, no getComputedStyle) and catch both.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_dom_change_signal_js
_DOM_CHANGE_SIGNAL_JS = """() => {
    const all = document.querySelectorAll('*');
    let classCount = 0;
    for (const el of all) classCount += el.classList.length;
    return all.length + '|' + document.body.textContent.length + '|' + classCount;
}"""


def _is_navigation_context_error(exc: Exception) -> bool:
    """Whether `exc` is Playwright's "JS execution context was torn down" error.
    Details: docs/dev/crawlers/crawl4ai_crawler.md#_is_navigation_context_error
    """
    msg = str(exc).lower()
    return "context was destroyed" in msg and "navigation" in msg


async def _wait_for_new_content(page, ceiling_seconds: float) -> None:
    """Poll a cheap DOM-change signal in short steps, returning once it has
    changed at least once AND held steady for `_STABLE_HOLD_SECONDS` -
    not on the first sign of change, and not after just one poll step of
    quiet either.
    An async fetch-then-render flow (click a submit button -> optimistic
    loading state -> network round-trip -> real content swaps in) produces
    at least two DOM changes in sequence, not one, and the *first* one can
    itself plateau just long enough to look settled before the real one
    arrives - live-verified on empanad.app (2026-08-11): after clicking
    into the order flow, an intermediate loading-state render held steady
    for ~0.13s before the real destination content (445 chars of body
    text, the actual components) appeared. A version of this function that
    required only one poll step (0.1s) of post-change quiet returned right
    on that intermediate plateau - shorter than the plateau itself - and
    persisted 0 components. `last_change_time` is re-armed on *every*
    change seen, not just the first, so a longer chain of intermediate
    states is ridden out the same way a single one is; the fixed hold
    window is what makes "quiet" mean "actually done," not merely
    "unchanged for one sample."
    Details: docs/dev/crawlers/crawl4ai_crawler.md#_wait_for_new_content
    """
    if ceiling_seconds <= 0:
        return
    try:
        last_signal = await page.evaluate(_DOM_CHANGE_SIGNAL_JS)
    except Exception:
        return  # torn-down context - let the caller's own extraction handle it
    last_change_time: Optional[float] = None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + ceiling_seconds
    while loop.time() < deadline:
        await asyncio.sleep(_ADAPTIVE_WAIT_STEP_SECONDS)
        try:
            signal = await page.evaluate(_DOM_CHANGE_SIGNAL_JS)
        except Exception:
            return
        now = loop.time()
        if signal != last_signal:
            last_change_time = now  # re-armed on every change, not just the first
        elif last_change_time is not None and now - last_change_time >= _STABLE_HOLD_SECONDS:
            return  # changed at least once, quiet for the full hold window since
        last_signal = signal


@dataclass
class Crawl4AICrawlerConfig:
    """Every tuning knob `Crawl4AICrawler` accepts, bundled into one object.
    Details: docs/dev/crawlers/crawl4ai_crawler.md#crawl4aicrawlerconfig
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
    # Details: docs/dev/crawlers/crawl4ai_crawler.md#viewport
    viewport_width: int = 800
    viewport_height: int = 600
    # Run axe-core after each navigation. Off during the crawl: it costs a
    # second per page and its contrast results are wrong with images blocked.
    # Details: docs/dev/crawlers/crawl4ai_crawler.md#audit_accessibility
    audit_accessibility: bool = False
    interaction_timeout_seconds: Optional[float] = None
    # Cap on the polite delay grown between navigations when the target
    # server itself is slowing down. `None` disables backoff (and the
    # circuit breaker below) entirely.
    # Details: docs/dev/crawlers/crawl4ai_crawler.md#backoff_ceiling_seconds
    backoff_ceiling_seconds: Optional[float] = 20.0
    # How long every worker pauses once the circuit breaker trips (a
    # navigation >= _SEVERE_SLOWDOWN_MULTIPLIER times the crawl's fastest).
    # Details: docs/dev/crawlers/crawl4ai_crawler.md#circuit_breaker_cooldown_seconds
    circuit_breaker_cooldown_seconds: float = 10.0


class Crawl4AICrawler:
    """Owns one crawl4ai `AsyncWebCrawler` for the lifetime of an `async with` block.
    Details: docs/dev/crawlers/crawl4ai_crawler.md#crawl4aicrawler
    """

    def __init__(
        self,
        config: Optional[Crawl4AICrawlerConfig] = None,
        throttle: Optional[TargetLoadThrottle] = None,
    ) -> None:
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
        # `throttle` lets Crawl4AICrawlerPool inject one shared instance across
        # every browser process it owns - one target server, one load signal,
        # regardless of how many physical browsers are watching it.
        # Details: docs/dev/crawlers/target_load_throttle.md#module
        self._throttle = throttle or TargetLoadThrottle(
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
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#__aenter__-browserconfig
        browser_config = BrowserConfig(
            headless=self.headless,
            light_mode=True,
            memory_saving_mode=True,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
        )
        self._crawler = AsyncWebCrawler(config=browser_config)
        # Hooks must be registered before __aenter__() is awaited below.
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#__aenter__-hook-order
        strategy = self._crawler.crawler_strategy
        strategy.set_hook("before_retrieve_html", self._before_retrieve_html)
        strategy.set_hook("on_execution_ended", self._on_execution_ended)
        # Always registered - on_page_context_created also folds in logging.
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#__aenter__-single-slot-hooks
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
        its own worker count. Details: docs/dev/crawlers/target_load_throttle.md#target_slowdown_ratio
        """
        return self._throttle.target_slowdown_ratio

    def _log_only_hook(self, hook_name: str):
        """Build a hook callback that only logs to `self.debug_log`.
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_log_only_hook
        """

        def hook(*args, **kwargs):
            # Plain sync callable - crawl4ai's execute_hook calls either way.
            self.debug_log.log_hook_from_raw(hook_name, args, kwargs)
            return args[0] if args else None

        return hook

    async def _on_page_context_created(self, page, context, config, **kwargs):
        """Installs block_images's route handler; fires on every `arun()` call.
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_on_page_context_created
        """
        if self.block_images and not getattr(
            page, "_pragma_image_block_installed", False
        ):
            await page.route("**/*", self._maybe_abort_media_request)
            page._pragma_image_block_installed = True
        if self.interaction_timeout_seconds is not None:
            # Changes Playwright's own no-explicit-timeout fallback.
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#_on_page_context_created-timeout
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
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_retry_empty_extraction
        """
        if data.get("components") or data.get("links"):
            return data
        try:
            node_count = await page.evaluate("() => document.querySelectorAll('*').length")
        except Exception:
            return data  # torn-down context - nothing to retry against
        if node_count < _EMPTY_EXTRACTION_MIN_NODES:
            return data

        await _wait_for_new_content(page, self.wait_seconds)
        retried = await run_extraction(page)
        found = len(retried.get("components") or []) + len(retried.get("links") or [])
        if self.debug_log:
            self.debug_log.log_hook(
                "empty_extraction_retry", nodes=node_count, found_on_retry=found
            )
        return retried if found else data

    async def _before_retrieve_html(self, page, context, config, **kwargs):
        """Discovery point for a plain navigation pass (no `js_code` this call).
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_before_retrieve_html
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
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#audit_accessibility
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
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_on_execution_ended
        """
        session_id = config.session_id or "default"
        await _wait_for_new_content(page, self.interaction_wait_seconds)
        try:
            data = await run_extraction(page)
        except Exception as exc:
            if not _is_navigation_context_error(exc):
                raise
            # Belt-and-suspenders: give a genuine navigation one more chance to settle.
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#_on_execution_ended-navigation-retry
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
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#_on_execution_ended-fallback
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
        Details: docs/dev/crawlers/crawl4ai_crawler.md#discover_page
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
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#discover_page-network-capture
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
        page_state = PageState(
            url=self._resolved_url(result, url),
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
        # The requested url, not page_state.url - see _save_markdown for why.
        self._save_markdown(url, result)
        return page_state

    @staticmethod
    def _resolved_url(result, requested_url: str) -> str:
        """`result.url` is always the requested URL; use `redirected_url` instead.
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_resolved_url
        """
        return getattr(result, "redirected_url", None) or result.url or requested_url

    def _save_markdown(self, session_id: str, result) -> None:
        """Save crawl4ai's markdown conversion of the page, if debug logging is on.
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_save_markdown
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
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_interact
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
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#_interact-network-capture
            capture_network_requests=True,
            page_timeout=int(self.page_timeout_seconds * 1000),
            prefetch=self.prefetch,
        )
        result = await self._crawler.arun(url=url, config=config)

        # result.success can be False for reasons unrelated to our own action.
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#_interact-success-signal
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

        raw_events = getattr(result, "network_requests", None) or []
        page_state = PageState(
            url=self._resolved_url(result, url),
            title=data.get("title", ""),
            metadata=data.get("metadata", {}),
            components=data.get("components", []),
            links=data.get("links", []),
            description=data.get("description", ""),
            network_requests=filter_meaningful_requests(raw_events),
            text_content=data.get("text_content", []),
        )
        self._save_markdown(
            url, result
        )  # the requested url, not page_state.url - see discover_page()
        return page_state

    async def resync(self, url: str, session_id: str) -> PageState:
        """Re-run discovery against the current live DOM; no action, no navigation.
        Details: docs/dev/crawlers/crawl4ai_crawler.md#resync
        """
        js_code = f"{_ACTION_MARK} = {{success: true}};"
        return await self._interact(url, session_id, js_code)

    async def click(self, url: str, session_id: str, selector: str) -> PageState:
        """Click `selector` within the session and return the new `PageState`.
        Details: docs/dev/crawlers/crawl4ai_crawler.md#click
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
        Details: docs/dev/crawlers/crawl4ai_crawler.md#fill
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
        Details: docs/dev/crawlers/crawl4ai_crawler.md#close_session
        """
        if self._crawler is None:
            raise RuntimeError(
                "Crawl4AICrawler must be used as an async context manager"
            )
        await self._crawler.crawler_strategy.kill_session(session_id)
