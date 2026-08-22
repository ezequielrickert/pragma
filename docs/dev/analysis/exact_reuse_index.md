# analysis/exact_reuse_index.py

## module

Interact-once tracking for `pragma dynamic`'s live interact sweep -
issue #135's design, wired for real (issue #140). A `Component` row
reused across 2+ pages - the exact tier's own definition, the same
criterion `analysis/component_matching_pipeline.py::_leaf_merge_groups`
merges rows on, made visible again at read time - gets interacted with
at most once, ever, per run: the first successful interaction with it
marks it interacted in memory (mirroring `record_component_interaction`'s
own `c.interacted = true` write), and every other page rendering the
same canonical row gets its outcome inferred instead of independently
re-clicked. Deliberately not routed through
`analysis/family_sampling.py::FamilySampler` - a family is several
*distinct* components judged merely similar; exact reuse is the *same*
canonical `Component` row rendered on several pages, a stronger claim
that earns a stronger inference.

## reuseentry

One canonical `Component` reused across `locations`. `interacted`
starts at whatever the ledger already knew (a prior run's real
interaction), then flips the instant this run interacts with it
anywhere - checked and set synchronously, with no `await` in between, so
two concurrent page workers racing the same canonical component can't
both decide to interact.

## siblings_of

Every other page this same canonical component also renders on - what
an inferred `NAVIGATES_TO` gets written for once this run's one real
interaction resolves.

## exactreuseindex

`(page_key, live component) -> ReuseEntry` for every canonical
`Component` rendered on 2+ pages - built once per `pragma dynamic` run
from `generators/ledger.py::flat_component_ledger`'s output, the same
snapshot `analysis/family_sampling.py::FamilySampler` is built from. A
component rendered on exactly one page is never exact-tier reuse -
nothing to infer, so it's absent from this index entirely and `lookup`
returns `None` for it, same as when clustering never ran.

## skipped

Every location the interact sweep skipped as an already-interacted
exact-tier reuse - kept as data, not just a print line, the same
reasoning `FamilySampler.skipped` follows, so a run summary can report
it.

## lookup

The reuse entry a live-discovered component belongs to, or `None` when
it isn't part of any exact-tier reuse. Matches by `component_identity()`
(tag/role/name/form/text), not by DOM path - the same content-identity
matching `_index_family_members` uses, and for the same reason: `path`
churns across separate `discover_page()` reloads.
