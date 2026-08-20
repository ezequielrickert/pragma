# `master` adds `llms.txt` + `manifest.json`, pins the short-hash algorithm

**Status**: accepted

The format audit's section 3.13 adds `llms.txt` and `manifest.json` alongside `master.md` (which
stays as-is — this is an addition, not a migration). Neither the llms.txt spec nor any prior ticket
in this map gives ordering guidance or ID-algorithm specifics, so this ADR locks pragma's own
conventions for both, confirms `master.md`'s banner already follows a decision `coverage` made, and
closes a gap the `manifest.json` checksum work surfaced: five separate tickets minted a
`<hash>`-suffixed ID without ever pinning which algorithm.

Decided, resolving the ticket's three open points (plus the short-hash amendment):

**1. `llms.txt` Structure.** Sections mirror `CONTEXT.md`'s own document taxonomy rather than an
invented classification — llmstxt.org's spec gives no ordering or grouping guidance of its own
(confirmed against the spec text directly), so this is pragma's convention, not a spec requirement:
`## Source Documents` (every JSON/JSON-LD/YAML source document and projection — the machine-checkable
ground truth), `## Views` (rendered `.md` files), `## Optional` (rule catalogs and tooling-facing
projections like `usability.sarif.json`/`architecture.cyclonedx.json` — not needed for an LLM's own
understanding of the site, only for CI tooling), using the spec's own documented `## Optional`
convention for skippable, lower-priority links. Within each section, links are ordered by the
wayfinder map's own ticket-resolution order (`coverage`, `export`, `tree`, `openapi`, `tokens`,
`catalog`, `architecture`, `data-model`, `prd`, `usability`, `accessibility`, `gherkin`, `flows`), a
real established sequence rather than an arbitrary alphabetical one.

**2. `manifest.json` Shape.** One entry per document:

```json
{
  "path": "coverage.json",
  "kind": "source",
  "format": "JSON Schema 2020-12",
  "status": "on",
  "checksum": "sha256:<hex>"
}
```

`kind` is a machine enum (`source`/`view`/`rule-catalog`/`projection`) mirroring `CONTEXT.md`'s
document taxonomy — one word per concept, not the glossary's prose Title Case, since the exact
string casing is an implementation detail that belongs here, not in `CONTEXT.md`. `status` mirrors
`core/config.py`'s live `documents` list and its individual off-by-default flags (`export_json`,
etc.) at generation time — never a second, hand-maintained flag that could drift from what actually
generated. `format` cites the specific external standard and version (`"OpenAPI 3.1.0"`,
`"CALM 1.2"`, `"EARL 1.0"`, ...). `checksum` is the full SHA-256 of the generated file's bytes,
matching the content-integrity convention already in code
(`spiders/content/payload_capture.py::hashlib.sha256`) — a different use case from the short-hash ID
family (point 4), which needs a short, readable identifier, not a collision-resistant file digest.

**3. `master.md`'s Banner.** Not a new decision — `coverage`'s ADR-0001 already locked "every
generated document's banner becomes a template render of `coverage.json`'s numbers." `master.md`
follows that same policy; there was never a live coverage-score-vs-generic-text fork here to resolve.

**4. Short-Hash Algorithm (amendment to ADR-0003, ADR-0009, ADR-0013).** `SCR-<hash>`/`template_hash`
(`tree`, ADR-0003), `REQ-<hash>` (`prd`, ADR-0009), and `EP-<hash>`/`MOD-<hash>` (`gherkin`,
ADR-0013) each minted a deterministic ID without ever specifying which hash algorithm produces it.
Pinned now to `sha1(...)[:10]` — the algorithm already used for exactly this purpose elsewhere in
the codebase (`spiders/content/component_matching.py`), not a new choice invented for this ticket.
See `CONTEXT.md`'s new **Short hash** entry: every future deterministic ID in this pipeline reuses
this one algorithm rather than each ticket picking its own.

Wayfinder ticket: [master: lock llms.txt + manifest.json shape](https://github.com/ezequielrickert/pragma/issues/79),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
