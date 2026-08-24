# analysis/family_sampling.py

## module

Family-aware component indexing for `pragma dynamic`. `pragma cluster`
groups repeating components (navbar links, footer buttons, ...) into
`ComponentFamily` patterns; `pragma dynamic` used to read that grouping
back here to skip redundant interaction, sampling only `max_samples`
instances per family instead of clicking/filling every one.

**Update - issue #215, the skip dropped:** the same shape of bug #214
found in `Frontier`'s content-identity dedup
(`docs/dev/spiders/orchestration/page_visitor/frontier.md#frontier`) - a
family groups components by structural/content similarity, which can't
tell "the same repeating boilerplate control" apart from "a genuinely
distinct sibling that happens to render the same way." Live verification
on mapadeprofesionales.com found exactly that: every repeated
professional card's own "Conectar"/favorite/share button clusters into
one `button/button` family, so only the first `max_samples` cards' worth
of those buttons ever got a real click. `should_interact` now always
returns `True` - every family member gets a real interaction attempt.
The family index itself (`pragma cluster`'s own `ComponentFamily`
records, and `_index_family_members` below) is untouched; only the
*skip* is gone, per the same standing direction as #214.

## default_max_samples_per_family

`3` - no longer consulted by `should_interact` (issue #215), kept only
for `FamilySampler.__init__`'s existing signature/callers. A future
convergence signal (map #211's Not yet specified) may reintroduce a use
for it.

## skippedinstance

One component the sampler would have skipped under the old
max-samples-per-family rule - kept as a type for `FamilySampler.skipped`'s
sake, though issue #215 means nothing ever populates it now.

## familysampler

Indexes each component's `pragma cluster` family membership. Built once
per run from `pragma cluster`'s output; `should_interact` is called once
per component the interact sweep encounters live, via
`PageVisitor._family_sampler`
(`docs/dev/spiders/orchestration/page_visitor/visitor.md#_family_sampler`).

## should_interact

Always `True` (issue #215) - see this file's own module note above for
why. Still looks up and counts family membership (`_member_family`,
`_sample_counts`) even though nothing gates on it any more, purely as
bookkeeping a future convergence signal could build on without
re-deriving the lookup from scratch.

## _index_family_members

A family's own `member_paths` only carries `(page_key, path)` - `path`
is a live DOM selector that churns across separate `discover_page()`
reloads (see
docs/dev/spiders/orchestration/page_visitor/frontier.md#frontier's
"History" section), so it can't be matched directly against a fresh
interact-sweep component. `component_identity` is what survives that reload; this
resolves each member's stored path back to the identity its ledger
record had at clustering time, via `components` (the same flat ledger
`pragma cluster` clustered from) - reconciled through each member's
canonical `id` (issue #140) rather than recomputed per `(page_url,
path)` in isolation: descriptive fields live on the `Component` node
itself since #136, so every location a given id renders at reports the
identical identity, and resolving through the id makes that invariant
explicit instead of relying on it by accident.
