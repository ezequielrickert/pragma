# analysis/component_clustering.py

## module

Extracted from `core/engine.py::_apply_component_families` so `pragma
cluster` (`core/cluster_engine.py::ClusterEngine`, a standalone command)
and `Engine._run_async` (the fused legacy run) share one implementation
instead of two copies drifting apart. Placed under `analysis/` rather
than `generators/`, next to `graph_projection.py` - both are whole-site,
post-crawl passes that read a finished graph store and write derived
facts back, as opposed to `generators/`'s per-document narration.

## apply_component_families

Three steps, always in this order: flatten the component ledger
(`generators/ledger.py::flat_component_ledger`), cluster it into
`ComponentFamily` objects (`generators/component_family.py::
build_component_families` - pure, no I/O, no LLM), then narrate each
family's purpose with the LLM (`generators/component_family_narrator.py::
narrate_family_purposes`) and write the result back via
`graph_store.record_component_families` (a full rebuild of the site's
family structure every call).

## known-purposes

Read before `record_component_families` wipes them: a family whose
members did not change keeps its previously narrated sentence rather
than buying it again with a fresh LLM call - what keeps a site crawled
in short resumable passes (or re-clustered by a separate `pragma
cluster` run) from re-narrating everything every pass.
