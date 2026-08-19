"""Argument-parsing helpers shared by more than one CLI command.
Details: docs/dev/core/cli_shared.md#module
"""
from __future__ import annotations

import argparse

from .config import PragmaConfig


def apply_budget_flags(config: PragmaConfig, args: argparse.Namespace) -> None:
    """Fold a command's `--max-pages-per-run`/`--max-minutes-per-run`/
    `--full` into `config.crawl_budget`.

    Kept out of the generic CLI-override dict every command already
    builds because these three are not `PragmaConfig` fields in their
    own right - they edit keys inside one field, and `--full` clears
    rather than sets. `--full` wins outright: it is the "ignore what the
    YAML says, run the whole thing" escape hatch, so combining it with a
    limit is a contradiction resolved in its favor.
    Details: docs/dev/core/cli_shared.md#apply_budget_flags
    """
    if args.full_run:
        config.crawl_budget = {}
        return
    if args.budget_pages is not None:
        config.crawl_budget["pages"] = args.budget_pages
    if args.budget_minutes is not None:
        config.crawl_budget["minutes"] = args.budget_minutes
