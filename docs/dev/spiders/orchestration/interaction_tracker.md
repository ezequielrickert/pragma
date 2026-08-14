# `spiders/orchestration/interaction_tracker.py`

## module

Split out from `mechanical_loop.py` because it's a self-contained
abstraction with its own default implementation - `graph_sink.py`'s
`GraphStoreInteractionTracker` is the persisted alternative
`MechanicalCrawler` swaps in when a `sink` is supplied.

## InteractionTracker

Consult-before-act seam (wiki/graph-based-crawl-tracking.md's "the ledger
must be consulted, not write-only," reapplied to a mechanical loop with no
per-step model decision to guard). `InMemoryInteractionTracker` is Phase
2's default; Phase 3 swaps in a `GraphStore`-backed implementation
(`graph_sink.GraphStoreInteractionTracker`) so the same accurate-frontier
property holds across a persisted multi-run crawl, not just within one
process.

## InMemoryInteractionTracker

Process-local `InteractionTracker` - everything lost on exit, same caveat
`InMemoryGraphStore` already documents. Fine for Phase 2's standalone
validation; not meant to survive into Phase 3+.
