# core/graph_store_resolution.py

## module

Shared `graph_store` resolution: create and connect the configured
backend, falling back to an in-memory store on a genuine failure - except
a cross-process `SiteLockError`, which must propagate rather than being
silently swallowed into a throwaway store (that would defeat the entire
point of the lock: a caller thinking it's writing to the real site
database while actually crawling into a store nobody will ever read).

This exact create-connect-fallback shape was duplicated verbatim across
`Engine`/`StaticEngine`/`DynamicEngine.from_config` before the lock
existed; factored out once it did, since a fourth copy - or a future
edit to one of the three - that forgot the `SiteLockError` guard would
silently reintroduce the failure mode this module exists to prevent.
`ClusterEngine`/`DocsEngine.from_config` don't use this: neither had a
fallback-to-memory branch to begin with, so an unguarded `connect()`
already propagates any error, `SiteLockError` included, with nothing to
special-case.

## resolve_graph_store

Create and connect `graph_store_name` for `site`, falling back to the
`"memory"` backend if that fails - unless the failure is a
`SiteLockError`, which is re-raised unchanged. `store_options` is
whatever `PragmaConfig.graph_stores` carries for the named backend
(e.g. `ladybug`'s own `directory` override), passed straight through as
keyword arguments to `GRAPH_STORE_REGISTRY.create`.
