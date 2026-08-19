# core/dynamic_cli.py

## module

`pragma dynamic` command: parse its args, run the resume-aware
interaction pass, report the result.

## parse_dynamic_args

Takes a URL, not a bare site - unlike `pragma cluster`, `pragma dynamic`
still has to know where to start a fused crawl when
`DynamicEngine.run`'s fallback path fires (nothing to resume). No
`--fresh` flag: purging the graph store's recorded state before an
interaction-only run would defeat the entire point of resuming from it.

## run_dynamic_command

`pragma dynamic <url>`: interact, don't scout or analyze - see
`DynamicEngine` for what that means in practice. Reports which mode the
run actually took (`resumed from static` vs. `independent full
discovery`) and, when any family sampling happened, how many families
and how many already-sampled instances got skipped.
