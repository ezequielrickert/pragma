# core/caching_graph_store.py

## module

Memoizes whole-site graph-store reads for the read-only phase of one `Engine`
run.

**What it fixes.** The post-crawl passes and every document generator read the
same handful of whole-site tables independently. `get_component_ledger` alone was
called about eight times per run - once per generator that needs it, plus twice
more in `Engine`'s own passes - and each call was a fresh full materialization
of the heaviest read in the project.

**Why it is safe, and why that safety is narrow.** This wraps the store *after*
the crawl has finished writing (see its construction in `Engine._run_async`).
None of the writes the wrapped passes still make - `record_component_families`,
`record_page_metrics`, `record_page_modules`, `record_entities` - touch any of
the reads it memoizes. That is the entire argument. It is **not** a
general-purpose cache and must not be reused earlier in a run, while the crawl
is still writing to the tables it holds.

`self.graph_store` on `Engine` is left untouched, so the real connection is
still what gets closed at the end.

### What is deliberately not cached

- **Parameterized reads** like `get_component_states(page_url)`. They vary per
  call and are not safe to memoize by method name alone.
- **Reads called once**, which buy nothing.
- **`get_page_metrics`**, and this one is the interesting exclusion. It is
  whole-site and zero-argument, so it has exactly the shape this cache is for -
  but `record_page_metrics`/`record_page_modules` write precisely what it reads,
  which is the one condition the safety argument above depends on being false.
  It would work today only because `_apply_graph_projection` happens to run
  before any document reads it. That is an ordering accident, not an invariant,
  and the read is one cheap `MATCH` over a page count in the tens. The exclusion
  is commented in the source so it does not look like an omission.

### Mechanics worth knowing

Everything not in `_CACHED_READS` - reads and writes alike - passes straight
through via `__getattr__`. The class defines no method sharing a name with
anything the store implements, so normal attribute lookup only ever finds
`__init__`/`__getattr__` and falls through correctly.

There is **no `site` in the cache key**. Unlike the retired DuckDB backend, the
wrapped store is already scoped to exactly one site by construction, so "per
method" is the whole key a zero-argument read needs.
