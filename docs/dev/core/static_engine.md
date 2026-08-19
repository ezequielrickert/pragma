# core/static_engine.py

## module

`pragma static`'s own entry point: a scout-only, `prefetch=true` crawl.
Deliberately its own class, not a mode on `Engine` - `Engine._run_async`
fuses crawling with document generation, and static's whole point is
*not* doing that: it captures a site's real static content (HTML, CSS,
routes) into the graph store and stops there. `pragma cluster`,
`pragma dynamic`, and `pragma docs` all resume from what this writes,
not from anything this class returns.

## staticrunresult

A summary of what landed in the graph store, not a document - static
generates none.

## staticengine

Wires a graph store and runs one site's scout-only crawl.

## from_config

Resolves the graph store named in `config` and wires a `StaticEngine`
around it. Same site-derivation convention as `Engine.from_config`
(`urlparse(url).netloc`, slugified by the store itself) - the on-disk
key every later stage (`cluster`, `dynamic`, `docs`) resumes against.

## run

Scouts every page reachable from `url`: real navigation, `prefetch=true`,
no click/fill (`MechanicalCrawlerConfig.scout_only`). Auto-triggers
login first via `spiders/browser/login.py::ensure_login_session` when
the site turns out to be gated - a crash here would defeat the point of
a first-class content-capture pass.
