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
from .page_extraction import DISCOVER_COMPONENTS_JS, run_extraction

# Hands a click/fill's own success/failure back to Python.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_action_mark
_ACTION_MARK = "window.__pragma_last_action__"

# Resource types safe to drop when Crawl4AICrawler.block_images is enabled.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_blocked_resource_types
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}

# _wait_for_new_content's poll step.
# Details: docs/dev/crawlers/crawl4ai_crawler.md#_adaptive_wait_step_seconds
_ADAPTIVE_WAIT_STEP_SECONDS = 0.1


def _is_navigation_context_error(exc: Exception) -> bool:
    """Whether `exc` is Playwright's "JS execution context was torn down" error.
    Details: docs/dev/crawlers/crawl4ai_crawler.md#_is_navigation_context_error
    """
    msg = str(exc).lower()
    return "context was destroyed" in msg and "navigation" in msg


async def _wait_for_new_content(page, ceiling_seconds: float, baseline_count: Optional[int]) -> None:
    """Poll in short steps for the first sign of new content, instead of
    always sleeping the full ceiling.
    Details: docs/dev/crawlers/crawl4ai_crawler.md#_wait_for_new_content
    """
    if ceiling_seconds <= 0:
        return
    deadline = asyncio.get_running_loop().time() + ceiling_seconds
    while asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(_ADAPTIVE_WAIT_STEP_SECONDS)
        try:
            count = len(await page.evaluate(DISCOVER_COMPONENTS_JS))
        except Exception:
            return  # torn-down context - let the caller's own extraction handle it
        settled = count > 0 if baseline_count is None else count != baseline_count
        if settled:
            return


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
    interaction_timeout_seconds: Optional[float] = None


class Crawl4AICrawler:
    """Owns one crawl4ai `AsyncWebCrawler` for the lifetime of an `async with` block.
    Details: docs/dev/crawlers/crawl4ai_crawler.md#crawl4aicrawler
    """

    def __init__(self, config: Optional[Crawl4AICrawlerConfig] = None) -> None:
        config = config or Crawl4AICrawlerConfig()
        self.headless = config.headless
        self.interaction_wait_seconds = (
            config.wait_seconds if config.interaction_wait_seconds is None else config.interaction_wait_seconds
        )
        self.wait_seconds = config.wait_seconds
        self.debug_log = config.debug_log
        self.page_timeout_seconds = config.page_timeout_seconds
        self.prefetch = config.prefetch
        self.block_images = config.block_images
        self.interaction_timeout_seconds = config.interaction_timeout_seconds
        self._crawler: Optional[AsyncWebCrawler] = None
        # session_id -> extraction dict, populated by whichever hook last ran.
        self._stash: Dict[str, Dict[str, Any]] = {}

    async def __aenter__(self) -> "Crawl4AICrawler":
        self._crawler = AsyncWebCrawler(config=BrowserConfig(headless=self.headless))
        # Hooks must be registered before __aenter__() is awaited below.
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#__aenter__-hook-order
        strategy = self._crawler.crawler_strategy
        strategy.set_hook("before_retrieve_html", self._before_retrieve_html)
        strategy.set_hook("on_execution_ended", self._on_execution_ended)
        # Always registered - on_page_context_created also folds in logging.
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#__aenter__-single-slot-hooks
        strategy.set_hook("on_page_context_created", self._on_page_context_created)
        if self.debug_log:
            strategy.set_hook("on_browser_created", self._log_only_hook("on_browser_created"))
            strategy.set_hook("on_user_agent_updated", self._log_only_hook("on_user_agent_updated"))
            strategy.set_hook("on_execution_started", self._log_only_hook("on_execution_started"))
            strategy.set_hook("before_goto", self._log_only_hook("before_goto"))
            strategy.set_hook("after_goto", self._log_only_hook("after_goto"))
            strategy.set_hook("before_return_html", self._log_only_hook("before_return_html"))
        await self._crawler.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._crawler is not None:
            await self._crawler.__aexit__(exc_type, exc, tb)
            self._crawler = None

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
        if self.block_images and not getattr(page, "_pragma_image_block_installed", False):
            await page.route("**/*", self._maybe_abort_media_request)
            page._pragma_image_block_installed = True
        if self.interaction_timeout_seconds is not None:
            # Changes Playwright's own no-explicit-timeout fallback.
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#_on_page_context_created-timeout
            page.set_default_timeout(self.interaction_timeout_seconds * 1000)
        if self.debug_log:
            self.debug_log.log_hook_from_raw(
                "on_page_context_created", (page,), {"context": context, "config": config, **kwargs}
            )
        return page

    async def _maybe_abort_media_request(self, route) -> None:
        if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    async def _before_retrieve_html(self, page, context, config, **kwargs):
        """Discovery point for a plain navigation pass (no `js_code` this call).
        Details: docs/dev/crawlers/crawl4ai_crawler.md#_before_retrieve_html
        """
        # No prior snapshot for a fresh navigation - any content counts.
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#_wait_for_new_content
        await _wait_for_new_content(page, self.wait_seconds, baseline_count=None)
        session_id = config.session_id or "default"
        data = await run_extraction(page)
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
        # Pre-click count, so only a genuine change counts as settled.
        # Details: docs/dev/crawlers/crawl4ai_crawler.md#_wait_for_new_content
        pre_click = self._stash.get(session_id)
        baseline_count = len(pre_click["components"]) if pre_click else None
        await _wait_for_new_content(page, self.interaction_wait_seconds, baseline_count)
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
            action_result = {"success": False, "error": "could not read back action result"}
        else:
            # Marker never set - fall back to crawl4ai's own execution result.
            # Details: docs/dev/crawlers/crawl4ai_crawler.md#_on_execution_ended-fallback
            exec_success = bool(result) and result.get("success", False)
            action_result = (
                {"success": True, "navigated": True} if exec_success
                else {"success": False, "error": (result or {}).get("error", "js_code did not run")}
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

    async def discover_page(self, url: str, session_id: Optional[str] = None) -> PageState:
        """Navigate to `url` and return its `PageState`; no interaction.
        Details: docs/dev/crawlers/crawl4ai_crawler.md#discover_page
        """
        if self._crawler is None:
            raise RuntimeError("Crawl4AICrawler must be used as an async context manager")
        session_id = session_id or url
        config = CrawlerRunConfig(
            session_id=session_id,
            cache_mode=CacheMode.BYPASS,
            wait_for="css:body",
            page_timeout=int(self.page_timeout_seconds * 1000),
            prefetch=self.prefetch,
        )
        result = await self._crawler.arun(url=url, config=config)
        if not result.success:
            raise RuntimeError(f"crawl4ai navigation failed for {url!r}: {result.error_message}")

        data = self._stash.pop(session_id, {})
        page_state = PageState(
            url=self._resolved_url(result, url),
            title=data.get("title", ""),
            metadata=data.get("metadata", {}),
            components=data.get("components", []),
            links=data.get("links", []),
            description=data.get("description", ""),
            text_content=data.get("text_content", []),
        )
        # session_id, not page_state.url - see _save_markdown for why.
        self._save_markdown(session_id, result)
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
            raise RuntimeError("Crawl4AICrawler must be used as an async context manager")
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
            raise RuntimeError(f"crawl4ai interaction failed for {url!r}: {result.error_message}")
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
        self._save_markdown(session_id, result)  # session_id, not page_state.url - see discover_page()
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

    async def fill(self, url: str, session_id: str, selector: str, value: str) -> PageState:
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
