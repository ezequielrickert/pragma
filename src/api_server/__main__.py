"""Run with `python -m src.api_server` to start Module 3 as a standing local service.

Meant to be started once and left running (see ARCHITECTURE.md's "Module 3: Unified REST API"
lifecycle section) - not spawned per orchestrator run. Host/port come from env vars so a second
instance (or a non-default port) is a one-liner, not a code change.

**A running instance does not pick up code changes** - this bit us once already during
development (a PlaywrightScraper discovery fix silently had zero effect because the old server
process was still running from before the edit). Set PRAGMA_API_RELOAD=1 while iterating on
src/api_server/ or src/scrapers/playwright_scraper.py to have uvicorn watch files and restart
itself automatically; leave it unset for a normal standing-service run (a restart on every save
would drop the live browser session, the opposite of what this lifecycle model is for).
"""
import os

import uvicorn


def main() -> None:
    host = os.getenv("PRAGMA_API_HOST", "127.0.0.1")
    port = int(os.getenv("PRAGMA_API_PORT", "8765"))
    reload = os.getenv("PRAGMA_API_RELOAD", "") == "1"
    uvicorn.run("src.api_server.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
