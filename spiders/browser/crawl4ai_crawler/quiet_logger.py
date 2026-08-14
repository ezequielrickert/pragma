"""Silences crawl4ai's own noisy, non-actionable network-capture warning.
Details: docs/dev/spiders/browser/crawl4ai_crawler/quiet_logger.md#module
"""

from __future__ import annotations

from crawl4ai.async_logger import AsyncLogger

# crawl4ai's built-in response-capture hook has a dead-code bug: on a
# response whose body can't be read (routine for a fire-and-forget analytics
# beacon like google.com/ccm/collect), it raises UnboundLocalError against
# its own unassigned `text_body`, which the same function's outer except
# then logs under this tag - already caught, never affecting anything this
# project reads back from `network_requests`, so it's noise, not a signal.
# Details: docs/dev/spiders/browser/crawl4ai_crawler/quiet_logger.md#_CAPTURE_TAG
_CAPTURE_TAG = "CAPTURE"


class QuietCaptureLogger(AsyncLogger):
    """AsyncLogger that drops crawl4ai's own CAPTURE-tagged warnings.
    Details: docs/dev/spiders/browser/crawl4ai_crawler/quiet_logger.md#quietcapturelogger
    """

    def warning(self, message: str, tag: str = "WARNING", **kwargs) -> None:
        if tag == _CAPTURE_TAG:
            return
        super().warning(message, tag=tag, **kwargs)
