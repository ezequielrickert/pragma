"""`pragma docs` command: parse its args, generate documents from an
existing site DB, report the result.
Details: docs/dev/core/docs_cli.md#module
"""
from __future__ import annotations

import argparse
import sys

from .docs_engine import DocsEngine, DocsRunResult
from .config import PragmaConfig
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def parse_docs_args(argv: list) -> argparse.Namespace:
    """A site, not a URL: `pragma docs` reads a `pragma static` run
    already on disk, so there is nothing here to navigate to.
    Details: docs/dev/core/docs_cli.md#parse_docs_args
    """
    parser = argparse.ArgumentParser(
        prog="cli.py docs",
        description="Generate documents from a site's existing graph store - no crawling. "
        "Projects the navigation graph, then runs the same document pipeline the full "
        "crawl+analysis run does.",
    )
    parser.add_argument("site", help="Site slug/host to document, as written by `pragma static`")
    parser.add_argument("--config", "-c", dest="config_path", help="Path to a pragma YAML config file")
    parser.add_argument(
        "--agent", "--provider", "-p", dest="agent",
        help=f"Agent plugin ({', '.join(AGENT_REGISTRY.names())})",
    )
    parser.add_argument(
        "--graph-store", dest="graph_store",
        help=f"Graph store plugin ({', '.join(GRAPH_STORE_REGISTRY.names())})",
    )
    parser.add_argument("--out", "-o", dest="out_dir", help="Output folder for the generated documents")
    parser.add_argument(
        "--tree-ascii", dest="tree_ascii", action="store_true", default=None,
        help="Render the component-tree document with plain ASCII instead of Unicode box-drawing",
    )
    parser.add_argument(
        "--export-json", dest="export_json", action="store_true", default=None,
        help="Also write the full crawl graph as structured JSON alongside the prose documents",
    )
    return parser.parse_args(argv)


def run_docs_command(argv: list) -> None:
    """`pragma docs <site>`: project, then generate - see `DocsEngine`
    for what that means in practice.
    Details: docs/dev/core/docs_cli.md#run_docs_command
    """
    args = parse_docs_args(argv)
    overrides = {k: v for k, v in vars(args).items() if k not in ("site", "config_path")}
    config = PragmaConfig.load(cli_overrides=overrides, yaml_path=args.config_path)

    try:
        print(f"Generating documents for site: {args.site}")
        print(f"Wiring: agent={config.agent} graph_store={config.graph_store}")
        engine = DocsEngine.from_config(config, args.site)
        result: DocsRunResult = engine.run()
        if not result.documents:
            print("No documents were generated - see the errors above.")
        else:
            master = next((d for d in result.documents if d.name == "master"), None)
            if master:
                print(f"\nStart here -> {master.path}")
            for document in result.documents:
                if document is master:
                    continue
                print(f"  {document.title}: {document.path}")
        print(f"Run recorded in manifest: {result.manifest_path}")
        print(f"Run index updated: {result.index_path}")
    except Exception as exc:
        print(f"Critical error during documentation: {exc}")
        sys.exit(1)
