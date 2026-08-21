# `generators/evidence_log.py`

## module

`evidence-log.jsonl` - a per-run index of `interaction:<id>`/`har:<id>`
evidence citations, docs/adr/0017.

**Why AXTree/DOM snapshots aren't re-indexed here.** `tree` already made
those resolvable via `SCR-<hash>` plus a per-leaf `x-axtree-ref` JSON
Pointer (ADR-0003). Indexing them a second time here would be exactly the
duplicate-view anti-pattern this whole map exists to eliminate - one
resolution path per evidence kind, not two that could drift.

**Why `screenshot:` is reserved rather than skipped entirely.** Present
in the schema's `kind` enum (so a future document citing `screenshot:<id>`
validates against a real, named kind), never actually emitted - no
screenshot-capture instrumentation exists in this crawl today. The same
"in the vocabulary, absent from the data" choice `coverage.json`'s own
reserved fields made (ADR-0001).

## _interaction_summary / _request_summary

Kept as pure functions over the store's own evidence dicts, not folded
into `_interaction_row`/`_request_row` - `_interaction_summary` reads
`action`/`value`/`path`/`page_url`, `_request_summary` reads
`method`/`path`/`status`/`host`/`path_pattern`; splitting the string-
building out from the row-shaping keeps each function testable against
exactly the fields it actually uses.

## build_evidence_log

Two store reads, `interaction:` rows first, `har:` rows after - never
interleaved, so a reader scanning the file for one kind finds its ids
monotonic instead of scattered through the other kind's ids.

## EvidenceLogDocument

`extension = "jsonl"`, one JSON object per line - not a single JSON
array. Schema validation runs against the row *list* before line-
serialization (`_as_jsonl`), the same "validate the structure, then
choose the wire format" split `tree.axtree.json`'s own array-rooted
schema already established for a non-object root type.

No view document: ADR-0017 names no `## Document Split` point the way
`usability`/`accessibility`/`flows` do, and a Markdown rendering of "a
list of ids and one-line summaries" would carry no information a reader
couldn't get from the JSONL file itself just as easily - the exact
zero-new-information case ADR-0014 point 4 already ruled against for
`sequences`.
