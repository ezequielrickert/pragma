# `core/interactive_cli.py`

## module

`pragma interactive <site>` command: serve a site's already-generated documents as an editable
local dashboard - no crawl, no graph store connection, just the flat files under `out_dir` a prior
`static`/`docs`/full-analysis run already wrote (ticket #151, map #146).

## parse_interactive_args

A site, not a URL - same convention `docs_cli.py`'s own `parse_docs_args` uses, for the same
reason: there is nothing here to navigate to, only an existing run's files to serve.

## run_interactive_command

Resolves `out_dir` the same way every other subcommand does (`PragmaConfig.load`) - this command
still does no crawling and no graph store connection (unlike `docs_cli.py`, which needs both).
Ticket #153 added a real `Agent` resolution for the chat panel, reusing `DocsEngine.from_config`'s
own exact pattern: `AGENT_REGISTRY.create(config.agent, **provider_options)`, falling back to
`"mock"` on any initialization failure rather than crashing the whole session over a chat feature
someone might not even use this run.
