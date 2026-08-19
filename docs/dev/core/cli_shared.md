# core/cli_shared.py

## module

Argument-parsing helpers shared by more than one CLI command
(`cli.py`'s own flag-driven full run, `core/static_cli.py`). Split out
once a second command needed the same budget-flag folding logic `cli.py`
already had, rather than let it drift into two near-identical copies.

## apply_budget_flags

`--max-pages-per-run`/`--max-minutes-per-run` edit keys inside
`PragmaConfig.crawl_budget` rather than being fields in their own right,
and `--full` clears that dict outright rather than setting a value -
that's why this isn't folded into each command's generic
`cli_overrides` dict the way every other flag is. `--full` wins over an
explicit limit: it's the "ignore what the YAML says, run the whole
thing" escape hatch, so combining it with a limit is a contradiction
resolved in its favor.
