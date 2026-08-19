# core/cluster_engine.py

## module

`pragma cluster`'s own entry point - reads a site's already-crawled
graph store, groups its components into `ComponentFamily` patterns, and
writes them back. No crawling, no navigation: `pragma static` writes
the components this reads.

## clusterrunresult

Summary of what the graph store now holds, not a document - clustering
generates none.

## clusterengine

Wires an agent and a graph store, then clusters one site's already-
discovered components.

## from_config

Resolves the agent and graph store named in `config`, scoped to `site`
- a bare host/slug, not a URL, since clustering resumes against a site
a previous `pragma static` run already wrote rather than starting one
of its own. This is where the map's "does `dynamic`/`cluster`/`docs`
take a URL or a site slug" fog item settles: they resume, so a slug is
all they need.

## run

Clusters `site`'s current component ledger and stops - see
`analysis/component_clustering.py::apply_component_families` for the
actual algorithm. Warns (doesn't crash) when the site has no recorded
components - the "forgot to run `pragma static` first" case, or the
wrong `--graph-store` pointed at an empty backend.
