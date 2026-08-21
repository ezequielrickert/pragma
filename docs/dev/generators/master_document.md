# `generators/master_document.py`

## module

D12: the document that explains the other documents.

The decision behind it (`research/plan-generacion-de-documentos.md` H5)
was explicitly "both": keep generating every document separately, and
*also* write one that ties them together. Not one replacing the other -
someone who wants the API contract should open the API contract, and
someone opening `docs/` for the first time should not have to guess which
of ten files that is.

**Why it contains no LLM call.** The obvious temptation is to have the
model write a paragraph about what the application does. D1 already does
exactly that, at length, from the same graph. Two documents narrating the
same thing in different words is not twice the value - it is a
contradiction waiting to happen, and the reader has no way to know which
one is authoritative. This document answers a different question, "which
file do I open", and that question has a deterministic answer.

**docs/adr/0015, ticket #109.** `MasterDocument` now writes three files
instead of one - `master.md` (the index above, unchanged), `llms.txt`
(the same index, shaped for llmstxt.org's own convention), and
`manifest.json` (one entry per registered document, on or off, with a
real checksum for every file this run actually wrote). All three read
`request.produced`, never a second, independently-maintained list.

## MasterDocument

**Why it is not registered in `DOCUMENT_REGISTRY`.** Registering it would
make it schedulable among the ordinary documents - and it is the one
generator whose input is the other generators' *output*. Run in the middle
of the list, it would render an index of however many documents happened
to precede it, with no error and no missing file: silently wrong output,
which is the worst failure mode available. Keeping it out of the registry
makes that arrangement unrepresentable rather than merely discouraged.

The corollary is that it cannot be turned off in config. That is
intentional: it costs one file write and no model call, and a run whose
index is missing is harder to explain than one with an index nobody read.

## no-own-banner

An earlier revision rendered the coverage banner inside `generate`, which
double-printed it once the pipeline started applying the banner to every
Markdown document. The banner now lives in exactly one place
(`pipeline._with_banner`) and this generator produces its body only -
the same rule every other Markdown document follows.

## _gaps

The coverage banner says how much of the site was reached. This says which
*kinds* of question the document set does not answer at all - a different
axis, and the one a reader is most likely to mistake for a missing file.

Right now it says one thing: no WCAG audit is produced. That needs axe-core
run against each page at a realistic viewport with images enabled, which is a
measurement pass this pipeline does not have. The note also names the
absolute-threshold measurements that go with it (contrast ratios, touch
targets, spacing) and draws the line that matters: *relative* comparisons -
these three buttons disagree with each other - survive an 800x600
images-blocked crawl and are reported; absolute ones do not.

**Conditional on the document actually being absent.** Reviving D11 makes
this note disappear on its own, rather than leaving behind a claim someone
has to remember to delete. See `research/plan-segunda-ronda-de-documentos.md`
B2, where not reviving it was the recommendation rather than an oversight.

## _llms_section

`kind in ("rule-catalog", "projection")` before `kind == "view"`: a
projection is exactly the case docs/adr/0015 point 1 names by example
(`usability.sarif.json`, `architecture.cyclonedx.json`) as belonging in
`## Optional` despite the ADR's own top-line wording for `## Source
Documents` also mentioning "projection" - the concrete named examples are
what actually pins the rule, not the summary sentence above them.

## _render_llms_txt

Ordered within each section by `_resolution_rank(document.name)` (the
*registry* name - `"flows"`, not a specific output's own `"flows.xstate"`
`filename`), `document.filename` only as the tiebreaker for a generator
with more than one file in the same section. Sorting by `filename`
instead would scatter a multi-output generator's own files across the
resolution order essentially at random, since names like `"flows.xstate"`
and `"tree.aria"` aren't in ADR-0015's own list at all - only the bare
registry names are.

## _format_for

Added in ticket #116 (docs/adr/0023): `_FORMAT_BY_FILENAME`'s own exact
match still runs first, but a generator whose filename varies per output
(`decisions.adr/0001-...`, `decisions.adr/0002-...`, one per inferred/
assumed requirement) has no single key that table could hold - checked
against `_FORMAT_BY_FILENAME_PREFIX` instead, falling back to no
`format` entry when neither matches, same as before this existed.

## _build_manifest

Every registered name (`DOCUMENT_REGISTRY.names()`) gets an entry -
`status: "on"` when it's in `request.produced` this run, `"off"`
otherwise. An "off" entry carries only `name`/`status`: `path`/`kind`/
`checksum` describe a real file, and this run wrote none for it - not
even a best-guess `kind` from `_FORMAT_BY_FILENAME`, since that table
describes a *file*, and a document that never ran produced none. `master`
itself is never in `DOCUMENT_REGISTRY` (see `MasterDocument` above), so
it never appears in its own manifest either.
