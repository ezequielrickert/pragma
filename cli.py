#!/usr/bin/env python3
"""
Command-line interface for Pragma.
"""
from __future__ import annotations

import pathlib
import sys

from dotenv import load_dotenv

# Path setup to allow running from any cwd (cli.py lives at the project root)
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(override=True)

from core import bootstrap  # noqa: F401  -- populates the plugin registries
from core.app import run_app
from core.cluster_cli import run_cluster_command
from core.crawl_cli import run_crawl_command
from core.docs_cli import run_docs_command
from core.dynamic_cli import run_dynamic_command
from core.interactive_cli import run_interactive_command
from core.login_cli import run_login_command
from core.static_cli import run_static_command
from core.wizard import run_config_wizard

# Every subcommand `main()` recognizes - named here once so the no-match
# error path below can list them without duplicating the dispatch table.
# Details: docs/dev/cli.md#_subcommands
_SUBCOMMANDS = ("config", "login", "static", "cluster", "dynamic", "docs", "interactive", "crawl")


def main() -> None:
    """Bare invocation launches the menu app; `config` jumps to the wizard;
    `login` captures a session; `static` runs a content-capture crawl;
    `cluster` groups an already-crawled site's components into families;
    `dynamic` interacts with a site's frontier, resuming from `static`/
    `cluster` output when there is any; `docs` generates documents from an
    existing site DB with no crawl; `interactive` serves an already-documented
    site's own output as an editable local dashboard, no crawl or graph store
    connection either; `crawl` chains static -> cluster -> dynamic (never
    `docs`/`interactive` - both stay separate, explicit invocations). Any
    other invocation (a bare URL, unrecognized flags) errors, naming the real
    subcommands - the Legacy Engine's own bare-URL dispatch (`python3 cli.py
    <url>` running a fused crawl+synthesize pass directly) was retired along
    with `core/engine.py` itself (issue #242, subsumes issue #222): every
    invocation now names the phase it wants.
    Details: docs/dev/cli.md#main
    """
    argv = sys.argv[1:]
    if argv and argv[0] == "config":
        run_config_wizard()
        return
    if argv and argv[0] == "login":
        run_login_command(argv[1:])
        return
    if argv and argv[0] == "static":
        run_static_command(argv[1:])
        return
    if argv and argv[0] == "cluster":
        run_cluster_command(argv[1:])
        return
    if argv and argv[0] == "dynamic":
        run_dynamic_command(argv[1:])
        return
    if argv and argv[0] == "docs":
        run_docs_command(argv[1:])
        return
    if argv and argv[0] == "interactive":
        run_interactive_command(argv[1:])
        return
    if argv and argv[0] == "crawl":
        run_crawl_command(argv[1:])
        return

    if not argv:
        if sys.stdin.isatty():
            run_app()
            return
        print("Error: URL must be provided (positional arg, --url, YAML config, or URL env var)")
        sys.exit(2)

    print(f"Error: unrecognized command {argv[0]!r}. Available subcommands: {', '.join(_SUBCOMMANDS)}.")
    sys.exit(2)


if __name__ == "__main__":
    main()
