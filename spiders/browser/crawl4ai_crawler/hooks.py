"""crawl4ai hook callbacks: bridge its callback API into this project's
extraction pipeline and stash. Composed by Crawl4AICrawler, not inherited -
this collaborator has its own reason to change (crawl4ai's hook contract,
extraction-retry policy) independent of Crawl4AICrawler's own (the public
navigate/interact API).
Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#module
"""
from __future__ import annotations

import functools
from typing import Any, Dict, List

from ...content.accessibility_snapshot import capture_accessibility_snapshot
from ...content.page_extraction import run_extraction
from ..dom_settle import _is_navigation_context_error, _wait_for_new_content
from .config import Crawl4AICrawlerConfig
from .mutation_heuristics import looks_like_mutating_get

# Resource types safe to drop when Crawl4AICrawlerConfig.block_images is enabled.
# Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_blocked_resource_types
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}

# HTTP methods immutable mode intercepts and fulfills synthetically instead
# of letting reach the server.
# Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_mutating_methods
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# The synthetic response an intercepted mutating request gets back in
# immutable mode - decided by "Prototype the synthetic fulfill() response"
# (issue #57): `{}` is valid JSON (so a caller's `response.json()` never
# throws) and `200` reads as an ordinary success (so `response.ok` checks
# pass), at the cost of any field a caller reads back from the body coming
# back `undefined` - an accepted v1 trade-off, not a bug.
# Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_mode_gate_fulfill_body
_MODE_GATE_FULFILL_BODY = "{}"

# Hands a click/fill's own success/failure back to Python.
# Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_action_mark
_ACTION_MARK = "window.__pragma_last_action__"


class HookHandlers:
    """Owns the session_id -> extraction-dict stash and every crawl4ai hook
    callback that reads or writes it.
    Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#hookhandlers
    """

    def __init__(self, config: Crawl4AICrawlerConfig) -> None:
        self.wait_seconds = config.wait_seconds
        self.interaction_wait_seconds = (
            config.wait_seconds
            if config.interaction_wait_seconds is None
            else config.interaction_wait_seconds
        )
        self.debug_log = config.debug_log
        self.block_images = config.block_images
        self.mode = config.mode
        self.interaction_timeout_seconds = config.interaction_timeout_seconds
        # session_id -> extraction dict, populated by whichever hook last ran.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_stash
        self._stash: Dict[str, Dict[str, Any]] = {}
        # session_id -> mutations `_route_gate` blocked since the last time
        # this session's stash was popped - one page (and one session_id)
        # per Playwright route handler, so this is what lets a request the
        # network layer never saw be attributed back to the interaction
        # that tried to fire it. Issue #62.
        # Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_blocked_mutations
        self._blocked_mutations: Dict[str, List[Dict[str, str]]] = {}

    def pop(self, session_id: str) -> Dict[str, Any]:
        """Consume and return `session_id`'s stashed extraction, or `{}`.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#pop
        """
        return self._stash.pop(session_id, {})

    def log_only_hook(self, hook_name: str):
        """Build a hook callback that only logs to `self.debug_log`.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#log_only_hook
        """

        def hook(*args, **kwargs):
            # Plain sync callable - crawl4ai's execute_hook calls either way.
            self.debug_log.log_hook_from_raw(hook_name, args, kwargs)
            return args[0] if args else None

        return hook

    async def on_page_context_created(self, page, context, config, **kwargs):
        """Installs the combined per-request route handler; fires on every
        `arun()` call. Always installed, regardless of `block_images`/`mode`
        - `_route_gate` is a no-op pass-through when both are off, but it's
        one handler either way: Playwright only reliably chains one active
        router per pattern scope, so media-blocking and the mode-gate can't
        be two competing `page.route("**/*", ...)` calls.

        Bound with `config.session_id` baked in via `functools.partial`,
        not read off `route` itself - a `Route`/`Request` carries no
        session_id of its own, only the page/frame that issued it, and one
        page belongs to exactly one session for this crawler's whole
        lifetime, so capturing it once here is enough to attribute a
        blocked mutation back to the interaction that tried to fire it.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#on_page_context_created
        """
        if not getattr(page, "_pragma_route_gate_installed", False):
            session_id = config.session_id or "default"
            await page.route("**/*", functools.partial(self._route_gate, session_id=session_id))
            page._pragma_route_gate_installed = True
        if self.interaction_timeout_seconds is not None:
            # Changes Playwright's own no-explicit-timeout fallback.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#on_page_context_created-timeout
            page.set_default_timeout(self.interaction_timeout_seconds * 1000)
        if self.debug_log:
            self.debug_log.log_hook_from_raw(
                "on_page_context_created",
                (page,),
                {"context": context, "config": config, **kwargs},
            )
        return page

    async def _route_gate(self, route, session_id: str) -> None:
        """The one `page.route("**/*", ...)` handler this crawler installs,
        composing every per-request policy in priority order: media
        blocking first (an outright network-cost cut, independent of
        mode), then the immutable-mode mutation gate.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_route_gate
        """
        if self._is_blocked_media_request(route):
            await route.abort()
        elif self._is_blocked_mutation(route):
            self._blocked_mutations.setdefault(session_id, []).append(
                {"method": route.request.method, "url": route.request.url}
            )
            await route.fulfill(
                status=200, content_type="application/json", body=_MODE_GATE_FULFILL_BODY
            )
        else:
            await route.continue_()

    def _is_blocked_media_request(self, route) -> bool:
        return self.block_images and route.request.resource_type in _BLOCKED_RESOURCE_TYPES

    def _is_blocked_mutation(self, route) -> bool:
        if self.mode != "immutable":
            return False
        method = route.request.method
        if method in _MUTATING_METHODS:
            return True
        if method == "GET":
            headers = getattr(route.request, "headers", None)
            return looks_like_mutating_get(route.request.url, headers)
        return False

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
        Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#_retry_empty_extraction
        """
        if data.get("components") or data.get("links"):
            return data

        await _wait_for_new_content(page, self.wait_seconds)
        retried = await run_extraction(page)
        found = len(retried.get("components") or []) + len(retried.get("links") or [])
        if self.debug_log:
            self.debug_log.log_hook("empty_extraction_retry", found_on_retry=found)
        return retried if found else data

    async def before_retrieve_html(self, page, context, config, **kwargs):
        """Discovery point for a plain navigation pass - crawl4ai fires this
        hook on every `arun()` call, `js_only` or not, so `config.js_only`
        (never set by `discover_page`, always set by `_interact`) is what
        actually distinguishes the two, not the hook's own firing.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#before_retrieve_html
        """
        if config.js_only:
            # An interaction call - on_execution_ended does the correct
            # settle-wait + extraction for this case, after js_code has
            # actually run. Doing it again here, before js_code runs, can
            # never detect a DOM change (nothing has happened yet), so
            # _wait_for_new_content would always burn its full ceiling for
            # nothing - a real, measured ~wait_seconds tax on every single
            # click/fill/resync/go_back call across the whole crawl.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#before_retrieve_html-js-only-skip
            return page
        await _wait_for_new_content(page, self.wait_seconds)
        session_id = config.session_id or "default"
        # Discovery has no interaction of its own to attribute a block to
        # (record_component_interaction is only ever called for a click/
        # fill) - discard rather than let a page-load-time block leak
        # forward and get misattributed to whichever click happens next.
        self._blocked_mutations.pop(session_id, None)
        data = await run_extraction(page)
        data = await self._retry_empty_extraction(page, data)
        # Once per discovery, not per interaction - ADR-0003's snapshot
        # policy (one snapshot per screen in v1). js_only calls return above
        # before reaching here, so this never re-fires mid-visit.
        data["aria_snapshot_yaml"], data["axtree_json"] = await capture_accessibility_snapshot(page)
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

    async def on_execution_ended(self, page, context, config, result, **kwargs):
        """Discovery point right after `config.js_code` runs; resolves action success.
        Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#on_execution_ended
        """
        session_id = config.session_id or "default"
        await _wait_for_new_content(page, self.interaction_wait_seconds)
        try:
            data = await run_extraction(page)
        except Exception as exc:
            if not _is_navigation_context_error(exc):
                raise
            # Belt-and-suspenders: give a genuine navigation one more chance to settle.
            # Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#on_execution_ended-navigation-retry
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
            # Details: docs/dev/spiders/browser/crawl4ai_crawler/hooks.md#on_execution_ended-fallback
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
        # Popped, not peeked - a mutation `_route_gate` blocks belongs to
        # the one interaction that triggered it; leaving it in place would
        # re-attribute it to whatever this session's next click happens to
        # be. Issue #62.
        data["blocked_mutations"] = self._blocked_mutations.pop(session_id, [])
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
                blocked_mutations=len(data["blocked_mutations"]),
            )
        return page
