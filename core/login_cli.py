"""`pragma login` command: parse its args, run the capture, report the result.
Details: docs/dev/core/login_cli.md#module
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import urlparse

from spiders.browser.login import force_login_session


def parse_login_args(argv: list) -> argparse.Namespace:
    """Its own small parser rather than a case in the main run parser,
    since it takes none of a crawl run's flags (budgets, output dir,
    agent/graph-store wiring) and adding it there would make every one
    of those look like it applies here too.
    Details: docs/dev/core/login_cli.md#parse_login_args
    """
    parser = argparse.ArgumentParser(
        prog="cli.py login",
        description="Open a headed browser, sign in by hand, and cache the session for reuse.",
    )
    parser.add_argument("url", help="URL of the site to log into")
    return parser.parse_args(argv)


def run_login_command(argv: list) -> None:
    """`pragma login <url>`: always captures a fresh session, since running
    this command by hand is itself the explicit request to sign in. No
    `--headless` flag - there is no such thing as a headless interactive
    sign-in, so the capture browser is always visible.
    Details: docs/dev/core/login_cli.md#run_login_command
    """
    args = parse_login_args(argv)
    site = urlparse(args.url).netloc
    try:
        path = asyncio.run(force_login_session(args.url, site))
        print(f"Session for {site} saved to {path}")
    except Exception as exc:
        print(f"Critical error during login: {exc}")
        sys.exit(1)
