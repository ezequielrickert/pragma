"""`pragma cluster` command: parse its args, run clustering, report the result.
Details: docs/dev/core/cluster_cli.md#module
"""
from __future__ import annotations

import argparse
import sys

from .cluster_engine import ClusterEngine, ClusterRunResult
from .config import PragmaConfig
from .registry import AGENT_REGISTRY, GRAPH_STORE_REGISTRY


def parse_cluster_args(argv: list) -> argparse.Namespace:
    """A site, not a URL: clustering resumes against a `pragma static` run
    already on disk, so there is nothing here to navigate to.
    Details: docs/dev/core/cluster_cli.md#parse_cluster_args
    """
    parser = argparse.ArgumentParser(
        prog="cli.py cluster",
        description="Group a site's already-discovered components into reusable families, "
        "narrated by the LLM - reads and writes the graph store, no crawling.",
    )
    parser.add_argument("site", help="Site slug/host to cluster, as written by `pragma static`")
    parser.add_argument("--config", "-c", dest="config_path", help="Path to a pragma YAML config file")
    parser.add_argument(
        "--agent", "--provider", "-p", dest="agent",
        help=f"Agent plugin ({', '.join(AGENT_REGISTRY.names())})",
    )
    parser.add_argument(
        "--graph-store", dest="graph_store",
        help=f"Graph store plugin ({', '.join(GRAPH_STORE_REGISTRY.names())})",
    )
    return parser.parse_args(argv)


def run_cluster_command(argv: list) -> None:
    """`pragma cluster <site>`: read, group, narrate, write back - see
    `ClusterEngine` for what that means in practice.
    Details: docs/dev/core/cluster_cli.md#run_cluster_command
    """
    args = parse_cluster_args(argv)
    overrides = {k: v for k, v in vars(args).items() if k not in ("site", "config_path")}
    config = PragmaConfig.load(cli_overrides=overrides, yaml_path=args.config_path)

    try:
        print(f"Clustering components for site: {args.site}")
        print(f"Wiring: agent={config.agent} graph_store={config.graph_store}")
        engine = ClusterEngine.from_config(config, args.site)
        result: ClusterRunResult = engine.run()
        noun = "family" if result.families == 1 else "families"
        print(f"\nGrouped components into {result.families} {noun} for {result.site}.")
    except Exception as exc:
        print(f"Critical error during clustering: {exc}")
        sys.exit(1)
