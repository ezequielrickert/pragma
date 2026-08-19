# analysis/family_sampling.py

## module

Family-aware interaction sampling for `pragma dynamic`. `pragma cluster`
groups repeating components (navbar links, footer buttons, ...) into
`ComponentFamily` patterns; `pragma dynamic` reads that grouping back
here to skip redundant interaction on components already known to belong
to a repeating family, sampling only `max_samples` instances per family
instead of clicking/filling every one - the whole point of resuming from
`static` + `cluster` output instead of re-discovering the site from
scratch.

## default_max_samples_per_family

`3`, not `2` - the ticket's own "2-3 instances" call, resolved toward 3
so a family whose second sample happened to be atypical (a disabled
state, an empty search box) still has a third to compare it against.

## skippedinstance

One component the sampler decided not to interact with, kept as data
rather than only a print line - a caller (a run summary, a test) can
inspect what got skipped without scraping stdout.

## familysampler

Caps how many members of each `ComponentFamily` a dynamic run actually
interacts with. Built once per run from `pragma cluster`'s output;
`should_interact` is called once per component the interact sweep
encounters live, via `PageVisitor._family_sampler`
(`docs/dev/spiders/orchestration/page_visitor/visitor.md#_family_sampler`).

## should_interact

A component with no known family (never clustered, or clustering never
ran for this site) always returns `True` - sampling only ever narrows a
crawl that already has a family to sample from, never blocks one that
doesn't. Once a family's count passes `max_samples`, every further
instance is recorded into `self.skipped` and logged, one line per
skipped component - the ticket's own "logging every skipped instance"
requirement.

## _index_family_members

A family's own `member_paths` only carries `(page_key, path)` - `path`
is a live DOM selector that churns across separate `discover_page()`
reloads (see
docs/dev/spiders/orchestration/page_visitor/frontier.md#_navigation_trigger_identities),
so it can't be matched directly against a fresh interact-sweep
component. `component_identity` is what survives that reload; this
resolves each member's stored path back to the identity its ledger
record had at clustering time, via `components` (the same flat ledger
`pragma cluster` clustered from).
