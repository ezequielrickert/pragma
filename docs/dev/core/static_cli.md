# core/static_cli.py

## module

`pragma static` command wiring - argument parsing and the run/report
loop - kept out of `cli.py` itself, the same way `core/cluster_cli.py`
and `core/login_cli.py` are.

## parse_static_args

A content-capture crawl, not the full run: no agent, no output
documents, so it takes only the flags that still mean something without
either of those (graph store, budgets, concurrency, `--login`/
`--fresh`/`--headed`) - not `--agent`, `--out`, `--tree-ascii`, or any
of the document-generation flags `cli.py`'s own parser carries.

## run_static_command

Thin wrapper around `core/static_engine.py::StaticEngine`: load config,
wire the engine, run it, print how many pages it scouted and which
login session (if any) it used.
