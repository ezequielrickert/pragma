# core/cluster_cli.py

## module

`pragma cluster` command wiring - argument parsing and the run/report
loop - kept out of `cli.py` itself, the same way `core/static_cli.py`
and `core/login_cli.py` are, so `cli.py` stays under the file-size-
audit's 300-line watch threshold as more commands accumulate.

## parse_cluster_args

Takes a `site` (a bare host/slug), not a URL: `pragma cluster` resumes
against whatever `pragma static` already wrote to that site's graph
store - there is nothing here to navigate to, so none of the crawl-tuning
flags (`--max-pages`, `--headed`, `--login`, ...) apply.

## run_cluster_command

Thin wrapper around `core/cluster_engine.py::ClusterEngine`: load
config, wire the engine, run it, print how many families it found.
