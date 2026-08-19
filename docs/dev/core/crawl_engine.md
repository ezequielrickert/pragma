# core/crawl_engine.py

## module

`pragma crawl`'s own entry point: a thin orchestrator chaining
`static → cluster → dynamic` against one URL. No new crawling/analysis
logic - just the three existing engines (`StaticEngine`, `ClusterEngine`,
`DynamicEngine`) called in sequence, each exactly as its own CLI command
would run it. Never runs `pragma docs` - the map's own Destination is
explicit that `docs` stays a fully separate, explicit invocation.

Each phase writes straight to the persistent graph store as it runs, so
"preserve partial results on failure" needs no rollback machinery here -
a phase's writes are already committed to disk by the time it returns.
This orchestrator's whole job is to stop the chain at the first failure
and say clearly which phase it was, rather than to protect data that was
never at risk.

## crawlrunresult

One result per phase that got to run, plus which phase (if any) stopped
the chain early. `static`/`cluster`/`dynamic` are `None` exactly for the
phases that never ran, so a caller can tell "ran and produced this" from
"never got here" without a separate flag per phase.

## succeeded

`True` iff every phase ran without raising - equivalent to
`failed_phase is None`, spelled out as its own property so a caller
doesn't have to remember which sentinel value means success.

## crawlengine

Chains `pragma static` -> `pragma cluster` -> `pragma dynamic` against
one URL, stopping at whichever phase fails first.

## from_config

Unlike every other engine's `from_config`, resolves nothing eagerly - no
agent, no graph store. Each phase resolves its own via its own
`from_config`, exactly as it would standalone; there is nothing shared
to wire up front. `StaticEngine`/`DynamicEngine` take `config` alone
(deriving `site` from `config.url` themselves); `ClusterEngine` takes
`(config, site)` - `CrawlEngine` derives `site` once, in `__init__`, and
passes it through only where a phase's own signature needs it.

## run

Runs `static`, then `cluster`, then `dynamic`, in that order, against
`url`. Stops and returns as soon as one phase raises - the phases that
already ran keep whatever they wrote; nothing after the failure ever
starts. Each phase gets its own `from_config` call rather than one
shared instance up front, so a phase that only exists to be skipped
(the ones after a failure) is never even constructed.

## _stop

Records which phase failed and why, and names the standalone command
that would resume from exactly what the earlier phases already wrote -
the practical version of "preserves partial results on failure":
nothing is lost, and the next step to take is spelled out rather than
left for the caller to work out.
