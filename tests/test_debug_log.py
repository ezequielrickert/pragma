"""Regression coverage for CrawlDebugLog.save_page_markdown's history file.

See wiki/graph-based-crawl-tracking.md's "separate the live snapshot from the
append-only audit trail" principle. Confirmed live on austral.edu.ar: a single
page visit calls `save_page_markdown` once per interaction within a session
(discover_page/_interact/resync all call it - see Crawl4AICrawler._save_markdown),
not just once per page. A snapshot that captured real discovered content
(e.g. a component's revealed items) was silently lost the moment a *later*,
possibly unrelated interaction in the same session overwrote the live
pages/{slug}.md file with different content - no trace it ever existed.
"""
import os

from src.crawlers.debug_log import CrawlDebugLog


def test_save_page_markdown_preserves_earlier_snapshots_in_history_file(tmp_path):
    log = CrawlDebugLog(str(tmp_path), site="example.com")
    try:
        url = "https://example.com/widget"

        # First snapshot: a component's items got discovered.
        log.save_page_markdown(url, "# Widget\n\n- item one\n- item two\n- item three")

        # A later, unrelated interaction in the same session re-saves the
        # same page's markdown - the live file is *meant* to be overwritten,
        # but the items snapshot must not simply vanish without a trace.
        log.save_page_markdown(url, "# Widget\n\n(items collapsed)")
    finally:
        log.close()

    live_path = os.path.join(str(tmp_path), "pages", "example.com_widget.md")
    history_path = os.path.join(str(tmp_path), "pages", "example.com_widget.history.md")

    assert os.path.exists(live_path)
    assert os.path.exists(history_path)

    live_content = open(live_path, encoding="utf-8").read()
    history_content = open(history_path, encoding="utf-8").read()

    # Live file legitimately only reflects the most recent save.
    assert "collapsed" in live_content
    assert "item one" not in live_content

    # History file must retain BOTH snapshots, in order - this is what fails
    # without the fix (overwrite-only save_page_markdown loses the first one).
    assert "item one" in history_content
    assert "collapsed" in history_content
    assert history_content.index("item one") < history_content.index("collapsed")
