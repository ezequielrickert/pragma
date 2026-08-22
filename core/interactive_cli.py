"""`pragma interactive <site>` command: serve a site's already-generated
documents as an editable local dashboard - no crawl, no graph store
connection, just the flat files under `out_dir` a prior
`static`/`docs`/full-analysis run already wrote (ticket #151, map #146).
Details: docs/dev/core/interactive_cli.md#module
"""
from __future__ import annotations

import argparse

from interactive.server import run_interactive_server

from .config import PragmaConfig


def parse_interactive_args(argv: list) -> argparse.Namespace:
    """A site, not a URL - same convention `docs_cli.py`'s own
    `parse_docs_args` uses, for the same reason: there is nothing here
    to navigate to, only an existing run's files to serve.
    Details: docs/dev/core/interactive_cli.md#parse_interactive_args
    """
    parser = argparse.ArgumentParser(
        prog="cli.py interactive",
        description="Serve a site's already-generated documents as an editable local dashboard - "
        "no crawling, no graph store connection. Run `pragma docs <site>` (or a full analysis) "
        "first if this site has no documents yet.",
    )
    parser.add_argument("site", help="Site slug/host to serve, as written by a prior docs/analysis run")
    parser.add_argument("--config", "-c", dest="config_path", help="Path to a pragma YAML config file")
    parser.add_argument("--out", "-o", dest="out_dir", help="Output folder the documents were written to")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Interface to bind the local server to (default: 127.0.0.1, local-only)",
    )
    parser.add_argument("--port", type=int, default=5050, help="Port to bind the local server to (default: 5050)")
    return parser.parse_args(argv)


def run_interactive_command(argv: list) -> None:
    """`pragma interactive <site>`: resolve `out_dir` the same way
    every other subcommand does (`PragmaConfig.load`), then hand off to
    the real server - this command itself does no crawling, no agent,
    no graph store, so none of those config sections are read.
    Details: docs/dev/core/interactive_cli.md#run_interactive_command
    """
    args = parse_interactive_args(argv)
    overrides = {"out_dir": args.out_dir} if args.out_dir else {}
    config = PragmaConfig.load(cli_overrides=overrides, yaml_path=args.config_path)

    run_interactive_server(config.out_dir, args.site, host=args.host, port=args.port)
