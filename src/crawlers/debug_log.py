"""Per-run debug logging for the crawl4ai pipeline: debug.md + pages/*.md.
Details: docs/dev/crawlers/debug_log.md#module
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def loggable_hook_details(args: tuple, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the small, markdown-friendly facts out of a raw hook call.
    Details: docs/dev/crawlers/debug_log.md#loggable_hook_details
    """
    details: Dict[str, Any] = {}
    if kwargs.get("url") is not None:
        details["url"] = kwargs["url"]
    response = kwargs.get("response")
    if response is not None:
        details["status"] = getattr(response, "status", "?")
    if "user_agent" in kwargs:
        details["user_agent"] = kwargs["user_agent"]
    if kwargs.get("html") is not None:
        details["html_length"] = f"{len(kwargs['html'])} chars"
    if "url" not in details:
        page = kwargs.get("page") or (args[0] if args and hasattr(args[0], "url") else None)
        if page is not None and hasattr(page, "url"):
            details["url"] = page.url
    return details


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _page_slug(url: str) -> str:
    """Filesystem-safe filename for one page's markdown snapshot.
    Details: docs/dev/crawlers/debug_log.md#_page_slug
    """
    cleaned = url.split("#")[0]
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in cleaned)
    return (safe or "page")[:200] + ".md"


class CrawlDebugLog:
    """Owns both debug artifacts for one crawl run - safe under concurrency.
    Details: docs/dev/crawlers/debug_log.md#crawldebuglog
    """

    def __init__(self, run_dir: str, site: str = "") -> None:
        self.run_dir = run_dir
        self.pages_dir = os.path.join(run_dir, "pages")
        os.makedirs(self.pages_dir, exist_ok=True)
        self._debug_path = os.path.join(run_dir, "debug.md")
        self._fh = open(self._debug_path, "a", encoding="utf-8")
        if self._fh.tell() == 0:
            self._fh.write(f"# Crawl debug log{f' — {site}' if site else ''}\n\n")
            self._fh.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n")
        self._fh.flush()

    def log_hook_from_raw(self, hook_name: str, args: tuple, kwargs: Dict[str, Any]) -> None:
        """`log_hook` for a hook registered purely for its logging side effect.
        Details: docs/dev/crawlers/debug_log.md#log_hook_from_raw
        """
        self.log_hook(hook_name, **loggable_hook_details(args, kwargs))

    def log_hook(self, hook_name: str, **details: Any) -> None:
        """Append one entry for a single hook firing, as a flat bullet list.
        Details: docs/dev/crawlers/debug_log.md#log_hook
        """
        self._fh.write(f"\n## [{_timestamp()}] `{hook_name}`\n\n")
        for key, value in details.items():
            self._fh.write(f"- **{key}**: {value}\n")
        self._fh.flush()

    def log_event(self, message: str, **details: Any) -> None:
        """Append a free-text entry not tied to a specific crawl4ai hook.
        Details: docs/dev/crawlers/debug_log.md#log_event
        """
        self._fh.write(f"\n## [{_timestamp()}] {message}\n\n")
        for key, value in details.items():
            self._fh.write(f"- **{key}**: {value}\n")
        self._fh.flush()

    def save_page_markdown(self, url: str, markdown: str) -> str:
        """Save crawl4ai's own markdown conversion of `url`'s current content.
        Details: docs/dev/crawlers/debug_log.md#save_page_markdown
        """
        slug = _page_slug(url)
        path = os.path.join(self.pages_dir, slug)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"<!-- {url} -->\n\n{markdown}")

        # ".md" -> ".history.md", not appended onto - see doc for both files' roles.
        history_slug = slug[:-len(".md")] + ".history.md" if slug.endswith(".md") else slug + ".history.md"
        history_path = os.path.join(self.pages_dir, history_slug)
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n---\n\n<!-- [{_timestamp()}] {url} -->\n\n{markdown}")

        self.log_hook(
            "page_markdown_saved",
            url=url,
            path=os.path.relpath(path, self.run_dir),
            history_path=os.path.relpath(history_path, self.run_dir),
            length=f"{len(markdown)} chars",
        )
        return path

    def close(self) -> None:
        self._fh.close()


def prune_old_runs(debug_logs_dir: str, slug: str, keep_last: Optional[int]) -> List[str]:
    """Delete this site's oldest run directories beyond `keep_last`.
    Details: docs/dev/crawlers/debug_log.md#prune_old_runs
    """
    if not keep_last or keep_last <= 0:
        return []
    if not os.path.isdir(debug_logs_dir):
        return []

    prefix = f"{slug}_"
    candidates = sorted(
        name
        for name in os.listdir(debug_logs_dir)
        if name.startswith(prefix) and os.path.isdir(os.path.join(debug_logs_dir, name))
    )
    to_delete = candidates[:-keep_last] if keep_last < len(candidates) else []

    removed: List[str] = []
    for name in to_delete:
        path = os.path.join(debug_logs_dir, name)
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    return removed
