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
document pipeline.

**The dashboard**:
The single interactive entry point planned for viewing every source
document. Built in three phases: (A) migrate documents to typed sources,
no viewer yet; (B) per-document best-fit renderer where one clearly wins
(e.g. Redoc for `openapi.yaml`), else a shared generic template; (C) all of
it stitched behind one dashboard shell as the single URL a reviewer opens.

**The format audit**:
Short name for `formatos-documentacion.docx`, the user-provided document
auditing the current 13-document pipeline and proposing the source/view
split. A proposal being negotiated, not a settled spec — its per-format
verdicts get reopened where genuinely contested, accepted where not.

**Existing-document wave**:
The 13 documents the pipeline generates today (`coverage`, `architecture`,
`prd`, `tree`, `openapi`, `catalog`, `tokens`, `data-model`, `flows`,
`usability`, `accessibility`, `gherkin`, `sequences`) plus the 3 documents
that exist but are off by default (`catalog-data`, `tokens-data`, `export`).
Reworked to the source/view split first.

**New-document wave**:
The 15 documents proposed by the format audit that don't exist in the
pipeline at all yet (`evidence-log`, `asyncapi`, `change-log`, `glossary`,
`redaction-log`, `test-plan`, `decisions.adr`, `risk-register`,
`content-inventory`, `performance-baseline`, `i18n-inventory`,
`browser-support-matrix`, `export.context.jsonld`, `llms.txt`,
`confidence-summary`). Added after the existing-document wave is settled.
