"""Per-run debug logging for the crawl4ai pipeline.

Two artifacts per crawl run, both under one timestamped directory
(`debug_logs/{slug}_{timestamp}/` by default - see `PragmaConfig.debug_logs_dir`
and `Engine._run_async`):

- `debug.md` - an append-only, human-readable record of every crawl4ai hook
  firing during the run (which hook, when, on what URL/session, with what
  result) - the append-only "audit trail" half of
  wiki/graph-based-crawl-tracking.md's "separate the live snapshot from the
  append-only audit trail" principle, applied to hook events instead of a
  research log. This is what to open when a crawl behaved unexpectedly and
  `GraphStore`'s final state alone doesn't explain *how* it got there.
- `pages/{page-slug}.md` - crawl4ai's own readable-markdown conversion of each
  page as last seen (overwritten on revisit, not appended - a live snapshot,
  not a history), so the actual textual content driving the crawl is directly
  inspectable without re-running anything.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _page_slug(url: str) -> str:
    """Filesystem-safe filename for one page's markdown snapshot - same
    scheme-strip discipline as `clean_url` (src/utils/urls.py), plus
    replacing path separators, since a URL is not a valid filename as-is."""
    cleaned = url.split("#")[0]
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in cleaned)
    return (safe or "page")[:200] + ".md"


class CrawlDebugLog:
    """Owns both debug artifacts for one crawl run.

    **Update — this class predates `page_concurrency` (MechanicalCrawler can
    now run several `_visit_page()` coroutines at once) and the note that
    used to stand here ("a single crawl is driven by one sequential
    coroutine, no concurrent `arun()` calls") is no longer true - kept only
    as history for why the plain-buffered-file-handle design below is still
    fine despite that:** every `log_hook`/`log_event`/`save_page_markdown`
    call here is a single synchronous method with no `await` inside it, so
    asyncio's cooperative scheduling (never preempts mid-call, only at an
    `await` point) makes each individual call atomic - concurrent workers'
    calls interleave in time, appending whole entries in whatever order they
    actually complete, never mid-write. `debug.md`'s append-only shape is
    genuinely safe under concurrency for exactly this reason.

    `pages/{slug}.md` was a real exception, since it isn't append-only:
    confirmed live on a real crawl (mapadeprofesionales.com,
    `page_concurrency=10`) that many distinct pages redirecting to the same
    destination could, before `Crawl4AICrawler._save_markdown` started
    keying by `session_id` instead of the post-redirect URL, overwrite one
    another's snapshot - a real information loss, not just interleaved
    output. See `MechanicalCrawler._in_flight` (mechanical_loop.py) for the
    deeper fix of the underlying race this symptom came from.
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

    def log_hook(self, hook_name: str, **details: Any) -> None:
        """Append one entry for a single hook firing. `details` is rendered as
        a flat bullet list, in insertion order - callers pass whatever's
        relevant/available for that specific hook (see `Crawl4AICrawler`'s
        per-hook logging calls), not a fixed schema every hook must fill in.
        """
        self._fh.write(f"\n## [{_timestamp()}] `{hook_name}`\n\n")
        for key, value in details.items():
            self._fh.write(f"- **{key}**: {value}\n")
        self._fh.flush()

    def log_event(self, message: str, **details: Any) -> None:
        """Append a free-text entry not tied to a specific crawl4ai hook -
        e.g. a page-visit summary from `MechanicalCrawler` itself, so the log
        reads as one continuous timeline rather than only ever showing raw
        hook noise with no higher-level narrative."""
        self._fh.write(f"\n## [{_timestamp()}] {message}\n\n")
        for key, value in details.items():
            self._fh.write(f"- **{key}**: {value}\n")
        self._fh.flush()

    def save_page_markdown(self, url: str, markdown: str) -> str:
        """Save crawl4ai's own markdown conversion of `url`'s current content
        to `pages/{slug}.md` (overwriting any previous snapshot of the same
        page - a live snapshot, not a history, since re-reading a page's
        current text is what's useful, not every past revision of it) and log
        a reference to it in `debug.md`. Returns the file path written.
        """
        path = os.path.join(self.pages_dir, _page_slug(url))
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"<!-- {url} -->\n\n{markdown}")
        self.log_hook(
            "page_markdown_saved",
            url=url,
            path=os.path.relpath(path, self.run_dir),
            length=f"{len(markdown)} chars",
        )
        return path

    def close(self) -> None:
        self._fh.close()
