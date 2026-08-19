# core/crawl_cli.py

## module

`pragma crawl` command: parse its args, chain static -> cluster ->
dynamic, report the result.

## parse_crawl_args

A superset of `static`'s own flags - `cluster`/`dynamic` take no flags
`static` doesn't already cover (`dynamic` reuses the same login/budget
knobs; `cluster` takes none at all). `--fresh` only ever reaches the
`static` phase in practice (`ClusterEngine`/`DynamicEngine.from_config`
don't read `config.fresh` at all), which is exactly the right scope for
it: the static phase's own reset already wiped the site before `cluster`
or `dynamic` ever connects.

## run_crawl_command

`pragma crawl <url>`: static -> cluster -> dynamic - see `CrawlEngine`
for what that means in practice. The top-level `try`/`except` here is a
backstop for a failure outside all three phases (config/wiring) -
a failure inside one of them is already caught by `CrawlEngine.run()`
itself and reported via `result.failed_phase` below, not by this.
