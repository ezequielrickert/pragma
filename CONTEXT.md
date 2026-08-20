# Pragma

Automated reconstruction of a legacy web system via crawl: discovers pages and
API traffic, then generates documentation describing what it found.

## Language

**Document**:
One output the doc-generation pipeline produces — a `DocumentGenerator` in
`core/documents.py`, registered in `DOCUMENT_REGISTRY`. Format-agnostic: a
document can be `.md`, `.yaml`, `.json`, `.feature`, whatever its generator
declares. Covers both source documents and view documents (below).
_Avoid_: artifact — no such concept exists in the code; using it here would
just be a second name for `Document`.

**Source document** (informal name for what the format-overhaul effort calls
"Capa 2"):
A document that is the typed, validated source of truth for one concern —
e.g. `coverage.json` against its own JSON Schema, `openapi.yaml`,
`requirements.json` in EARS syntax. Machine-checkable; other documents may
cite it, but it is never itself a render of something else.

**View document** ("Capa 3"):
A document mechanically derived from a source document by a deterministic
template — never hand-authored in parallel with the source it renders. Its
job is readability for a human, not truth; if it disagrees with its source
document, the source wins and the view is regenerated.

**Duplicate view**:
The anti-pattern the format-overhaul effort is eliminating: a document
written independently of a source document that covers the same ground, so
the two can silently diverge (today's `catalog.md` vs. the off-by-default
`catalog-data.json` is the reference example). Distinct from a
**standard-format document** — e.g. ACT Rules Format, `llms.txt`, MADR are
all Markdown-with-frontmatter *because their governing standard specifies
that as the format*, not because something is being duplicated. A
standard-format document is itself a source document, even though its
serialization happens to be Markdown.

**Evidence** ("Capa 1"):
Raw, immutable crawl output — HAR, WARC, screenshots, DOM/AXTree snapshots.
Not a `Document`: it isn't produced by a `DocumentGenerator` and nothing
renders it. Source documents may cite evidence (e.g. a requirement's
`derived_from` pointing at a HAR entry), but evidence itself sits outside the
document pipeline. `evidence-log` (ADR-0017) is a `Document` that indexes
evidence so those citations resolve — same relationship `export.json` has to
the graph (ADR-0002), not a second place evidence itself lives.

**The dashboard**:
The single interactive entry point for viewing every source document — static HTML generated at
doc-generation time, no running server, no build step, so both of its named audiences (a human
reviewer and Claude Code itself, reading files directly) can consume it the same way. Built in three
phases: (A) migrate documents to typed sources, no viewer yet; (B) per-document best-fit renderer
where one clears a real bar — ships as a single vendorable static asset (Redoc's standalone bundle
for `openapi.yaml` is the reference case), actively maintained, saves real effort over the
alternative — else a shared generic template; (C) all of it stitched behind one shell (ADR-0016): a
landing page leading with crawl-wide metrics (pages crawled vs. found, components interacted vs.
discovered, requirement confidence split, endpoint saturation — no forced denominator where
`coverage`'s ADR-0001 didn't give it one), then a card grid of every concern with its own
coverage/confidence at a glance, each card drilling into that concern's own page. No persistent nav
chrome — the landing page carries the navigation, not a sidebar or top bar shown everywhere.

**The format audit**:
Short name for `formatos-documentacion.docx`, the user-provided document
auditing the current 13-document pipeline and proposing the source/view
split. A proposal being negotiated, not a settled spec — its per-format
verdicts get reopened where genuinely contested, accepted where not.

**Existing-document wave**:
The 13 documents the pipeline generated before this overhaul (`coverage`, `architecture`,
`prd`, `tree`, `openapi`, `catalog`, `tokens`, `data-model`, `flows`,
`usability`, `accessibility`, `gherkin`, `sequences`) plus the 3 documents
that existed but were off by default (`catalog-data`, `tokens-data`, `export`).
Reworked to the source/view split first. One of the 13 has since folded into
its sibling rather than surviving as its own registered document: `sequences`
into `flows` (ADR-0014).

**Short hash**:
The `sha1(...)[:10]` convention behind every deterministic ID this pipeline mints —
`SCR-<hash>` (`tree`, ADR-0003), `template_hash` (`tree`, ADR-0003), `REQ-<hash>` (`prd`, ADR-0009),
`EP-<hash>`/`MOD-<hash>` (`gherkin`, ADR-0013), `CH-<hash>`/`MSG-<hash>` (`asyncapi`, ADR-0018).
Never invented per-document: five separate tickets minted a `<hash>`-suffixed ID without saying
which algorithm, until `master` (ADR-0015) pinned it as the one already used for exactly this
purpose elsewhere in the codebase (`spiders/content/component_matching.py`). Every future
deterministic ID reuses this, not a new one.

Consequence worth stating once, not rediscovered per-document (first surfaced by `change-log`,
ADR-0019): every Short hash is derived from an entity's *identity-defining* fields, so an entity
whose identity-defining fields change doesn't keep its ID and show up as "changed" — it becomes a
*different* ID, one no-longer-observed and one newly-discovered. Anything comparing one of these
IDs across two points in time (a diff, a cache, a `first_seen`/`last_seen` pair) inherits this: a
same-ID match already means "same identity," and a same-ID-different-field state means the entity's
identity held but some other property moved.

**`coverage_ref`**:
A pointer a document embeds to cite `coverage`'s numbers for the slice it covers, so a reader can
tell "this requirement came from a 20%-covered module" without leaving the citing document. Points
at a whole run (`run_id`) until per-module coverage exists — see `module_id`.

**`module_id`**:
The identifier a document uses to say "this belongs to module X." What a module *is* — path-prefix
clustering, falling back to detected graph community — was locked by `architecture`'s graph-metrics
ticket (ADR-0007); the literal ID string (`MOD-<slug>` for a path-prefix-derived module,
`MOD-<hash>` for one with no natural name) was locked by `gherkin` (ADR-0013), the first document
that needed a concrete format rather than just the derivation rule. A document written before either
ticket resolved reserves the field rather than inventing its own scheme; every document since cites
this one.

**Reserved field**:
A schema field that's present and typed but not yet populated with real data, because the crawler
has no instrumentation for it yet (e.g. `coverage.roles`, `coverage.blockers`). Distinct from a
dropped field: reserved means "the shape is locked so later documents can reference it now," dropped
means "no plan exists yet, don't pretend otherwise." See `docs/adr/0001-coverage-schema-scope.md`.

**The graph**:
The live property-graph store (`database/ladybug/`, backed by Kùzu) that every crawl writes into
and every generator reads from. Distinct from `export`: the graph is queried directly (e.g. for
FU-3 module-exclusion logic); `export` is a JSON-LD snapshot of it, generated once per run for
portability, not a second query engine.

**Projection**:
A document generated by reshaping pragma's own data — the graph, or another source document —
into an *external* standard's own schema, so the result is independently valid and useful outside
pragma itself (any CALM tool, any SARIF-consuming CI system), not just formatted for a person to
read. Examples: `architecture.calm.json`/`architecture.cyclonedx.json` (of the graph, ADR-0010),
`usability.sarif.json` (of `usability.earl.jsonld`'s findings, ADR-0011). Distinct from a
**snapshot** (`export.json`): a snapshot restates its origin in that origin's own native
vocabulary; a projection reshapes the same data into someone else's vocabulary, so two projections
of the same origin can look nothing alike. Still a source document (machine-checkable against the
external schema), not a view — a view's audience is a human; a projection's is another tool, and
truth still flows one-way from whatever it projects.
_Avoid_: export (that name is reserved for the graph snapshot specifically); view (a projection is
never hand-editable truth of its own, but its consumer is a tool, not a reader).

**Rule catalog**:
A source document whose content is fixed for a given rule-set version, not derived from any crawl —
e.g. `usability-rules.json` (hand-authored by whoever writes pragma's own checks) and
`accessibility-rules.json` (mechanically extracted from axe-core's own rule metadata, changing only
when pragma bundles a new axe-core version). Every other source document assumes it's regenerated
per crawl run from what that run found; a rule catalog breaks that assumption. Still
machine-checkable and still cited by other documents (a run's findings cite a rule by ID) — what
makes it a rule catalog is that its content tracks a rule set's own version, whether a person or a
third-party engine owns that version, not who or what originates the content.

**New-document wave**:
The 15 documents proposed by the format audit that don't exist in the
pipeline at all yet (`evidence-log`, `asyncapi`, `change-log`, `glossary`,
`redaction-log`, `test-plan`, `decisions.adr`, `risk-register`,
`content-inventory`, `performance-baseline`, `i18n-inventory`,
`browser-support-matrix`, `export.context.jsonld`, `llms.txt`,
`confidence-summary`). Added after the existing-document wave is settled.
