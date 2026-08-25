# core/dynamic_engine.py

## module

`pragma dynamic`'s own entry point: resume-from-DB interaction over a
site. Deliberately its own class, not a mode on `Engine` -
`Engine._run_async` still fuses discovery and interaction into one pass
with no resume capability. `DynamicEngine` resumes from whatever `pragma
static` (and, if it ran, `pragma cluster`) already wrote: when the graph
store has pages left `"Scouted"`, this interacts with exactly those. A
canonical `Component` reused across pages is still interacted with once,
ever, its outcome inferred onto every other page it renders on
(`analysis/exact_reuse_index.py::ExactReuseIndex`, issue #140) - that's
the same node, not a merely similar one. A merely similar, genuinely
distinct component belonging to a known family used to be
sample-and-skip capped (`analysis/family_sampling.py::FamilySampler`) -
issue #215 dropped that cap (the same shape of bug #214 found in
`Frontier`'s own content-identity dedup), so every family member now
gets a real attempt; `FamilySampler` still indexes membership, it just
never skips on the strength of it. When there's no prior `pragma static`
run for this site, this falls back to independent full
discovery+interaction, the same fused behavior `Engine` has always run.

## dynamicrunresult

A summary of what landed in the graph store, not a document - dynamic
generates none. `resumed_from_static` is the fallback-vs-resume signal
`run_dynamic_command` reports to the terminal; `families_sampled`/
`instances_skipped`/`exact_reuse_skipped` are `0` whenever clustering
never ran, since a component with no known family or reuse is always
interacted with. `instances_skipped` is also always `0` now regardless
of clustering (issue #215) - `families_sampled` still reports how many
families `pragma cluster` found, a historical name for what's now purely
a count, not a sampling outcome.

## dynamicengine

Wires an agent and a graph store, then interacts with one site's
frontier.

## from_config

Resolves the agent and graph store named in `config` and wires a
`DynamicEngine` around them. Same site-derivation convention as
`Engine.from_config`/`StaticEngine.from_config`
(`urlparse(url).netloc`) - the on-disk key this resumes against.

## _build_matching_state

Reads `generators/ledger.py::flat_component_ledger` once and builds both
`exact_reuse_index` and `sampler` from it - `exact_reuse_index` is the
one still-live gate; `sampler` (`FamilySampler`) no longer gates anything
(issue #215) but is still built so `families_sampled`/its own membership
index stay available. `exact_reuse_index` needs nothing beyond the
ledger itself - a component can be exact-tier reused via write-time
collapse alone (issue #136), without `pragma cluster` ever running - so
it's `None` only when the site has no components at all. `sampler`
additionally needs `graph_store.get_component_families()`; `None` when
that's empty (clustering never ran, or ran over a site with no
repeating patterns). The ledger is also what resolves each family
member's stored `(page_key, path)` back to a content-based identity (see
`analysis/family_sampling.py::_index_family_members`).

## run

`resumed = bool(self.graph_store.get_scouted())` is the whole
resume-vs-fallback decision: non-empty means a prior `pragma static` run
left pages `"Scouted"` for this site, so this run sets
`MechanicalCrawlerConfig.interact_only=True` and interacts with exactly
those pages, every member of every known family included (issue #215);
empty means there's nothing to
resume, so `interact_only` stays `False` and `MechanicalCrawler.crawl_site`
falls through to its own default fused `visit()` pass - full,
independent discovery+interaction, unchanged from what `Engine` has
always run. Auto-triggers login first via
`spiders/browser/login.py::ensure_login_session`, same as `StaticEngine.run`.
