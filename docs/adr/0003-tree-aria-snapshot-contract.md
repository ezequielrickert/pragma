# `tree` becomes a real ARIA snapshot, not a reshaped DOM tree

**Status**: accepted

The format audit's section 3.4 proposes replacing `tree`'s hand-written component tree —
today's `component_type`/`tag` labels nested by DOM position — with Playwright's `ariaSnapshot()`
(YAML) plus the CDP AXTree (JSON). Accepted in full, not as a relabeling: a version that kept
today's DOM-derived tags and just reshaped them into YAML nested-by-landmark would still be the
ad-hoc vocabulary the audit calls "reinventa la rueda," now in YAML clothing instead of Markdown.
The whole point of adopting this format is a stable, semantic vocabulary — role plus accessible
name, computed the way a screen reader would compute it — not a new serialization of the same DOM
tags. `ariaSnapshot()` is one call on `crawl4ai_crawler`'s underlying Playwright `Page` object: new
instrumentation, but small. Pragma's own interaction/request/redirect data rides along as
`x-`-namespaced extension properties on each leaf, the same convention `catalog` already uses for
`x-observed-variants`.

Decided, resolving the ticket's four open points:

**Screen-ID scheme.** `SCR-<hash>`, where the hash is a short truncation (e.g. `SCR-a4f9`) of
`database/ladybug/component.py`'s `route_shape`d URL, not a sequential counter assigned at
generation time. `route_shape` already collapses a session-token URL that changes every visit down
to the same canonical route, so hashing it is deterministic for free — the same route gets the same
ID on every run. A counter would drift the moment a second crawl discovers pages in a different
order, silently breaking `coverage`'s `coverage_ref`, `prd`'s `links.screens`, and `flows`'
`meta.screen`, all of which cite a screen ID across runs.

**Snapshot policy.** One snapshot per screen in v1, not one per screen-and-state — state detection
(empty/error/loading/forbidden/paginated) doesn't exist anywhere in the crawler today, the same gap
that made `coverage` drop its UI-state dimension entirely (ADR-0001). Unlike `coverage`, `tree`
reserves a `state` field on the snapshot (`default` today, always populated) rather than dropping
it: `usability` and `accessibility` findings will want to cite which state a finding was observed
in the moment state detection lands, and adding a `state` field to an existing snapshot format later
is cheaper than retrofitting that citation convention into three other documents after the fact.

**Duplicate/template detection.** Ships in v1. A structural hash — role and hierarchy only, text
content stripped — computed over each snapshot and stored as a `template_hash` field. This needs no
new crawler instrumentation; it's pure post-processing over the ARIA tree the snapshot already
built, and it gets the audit's "40 near-identical screens, 1 template" detection for free.

**Reference convention, ARIA YAML → AXTree JSON.** Per-leaf `x-axtree-ref`, a JSON Pointer
(`/nodes/42`) from the YAML leaf into that screen's AXTree JSON — not file-level pairing and not
positional correlation. File-level pairing only supports "open the whole AXTree for this screen";
positional correlation is implicit and breaks silently if either generator ever reorders its
traversal. A JSON Pointer costs one extra field per leaf and survives both generators evolving
independently, which a same-run-position assumption does not.

**Short-hash algorithm** (amendment, ADR-0015). `SCR-<hash>` and `template_hash` both named "a
deterministic hash" without saying which algorithm. Pinned to `sha1(...)[:10]`, matching the
algorithm already used for exactly this purpose elsewhere in the codebase
(`spiders/content/component_matching.py`) — see `CONTEXT.md`'s **Short hash** entry.

Wayfinder ticket: [tree: lock ARIA-snapshot/AXTree contract](https://github.com/ezequielrickert/pragma/issues/67),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
