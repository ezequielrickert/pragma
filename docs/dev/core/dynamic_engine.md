# core/dynamic_engine.py

## module

`pragma dynamic`'s own entry point: resume-from-DB, family-aware
interaction over a site. Deliberately its own class, not a mode on
`Engine` - `Engine._run_async` still fuses discovery and interaction
into one pass with no resume capability. `DynamicEngine` resumes from
whatever `pragma static` (and, if it ran, `pragma cluster`) already
wrote: when the graph store has pages left `"Scouted"`, this interacts
with exactly those, skipping redundant clicks/fills on components a
known family already covers (`analysis/family_sampling.py::FamilySampler`).
When it doesn't - no prior `pragma static` run for this site - it falls
back to independent full discovery+interaction, the same fused behavior
`Engine` has always run.

## dynamicrunresult

A summary of what landed in the graph store, not a document - dynamic
generates none. `resumed_from_static` is the fallback-vs-resume signal
`run_dynamic_command` reports to the terminal; `families_sampled`/
`instances_skipped` are `0` whenever clustering never ran, since a
component with no known family is always interacted with.

## dynamicengine

Wires an agent and a graph store, then interacts with one site's
frontier.

## from_config

Resolves the agent and graph store named in `config` and wires a
`DynamicEngine` around them. Same site-derivation convention as
`Engine.from_config`/`StaticEngine.from_config`
(`urlparse(url).netloc`) - the on-disk key this resumes against.

## _build_family_sampler

Reads `graph_store.get_component_families()`; `None` when it's empty
(clustering never ran, or ran over a site with no repeating patterns) so
`run`'s interact sweep never consults a sampler and interacts with every
eligible component as it always did before this ticket. Otherwise builds
a `FamilySampler` from the family list plus the flat component ledger
(`generators/ledger.py::flat_component_ledger`) - the same ledger
`pragma cluster` itself clustered from, needed to resolve each family
member's stored `(page_key, path)` back to a content-based identity (see
`analysis/family_sampling.py::_index_family_members`).

## run

`resumed = bool(self.graph_store.get_scouted())` is the whole
resume-vs-fallback decision: non-empty means a prior `pragma static` run
left pages `"Scouted"` for this site, so this run sets
`MechanicalCrawlerConfig.interact_only=True` and interacts with exactly
those pages (sampling known families); empty means there's nothing to
resume, so `interact_only` stays `False` and `MechanicalCrawler.crawl_site`
falls through to its own default fused `visit()` pass - full,
independent discovery+interaction, unchanged from what `Engine` has
always run. Auto-triggers login first via
`spiders/browser/login.py::ensure_login_session`, same as `StaticEngine.run`.
