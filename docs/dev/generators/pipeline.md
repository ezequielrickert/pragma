# `generators/pipeline.py`

## module

Runs the configured documents, then the master document.

**What this replaced.** `Engine._run_async` used to carry a literal block
per output file - build it, name it, write it, remember its path - and
`EngineRunResult` a field per file. Three documents was already repetitive;
`research/plan-generacion-de-documentos.md` plans ten. Now adding a
document is a generator module plus a name in `PragmaConfig.documents`,
and neither this file nor `Engine` changes.

## DocumentNaming

The three values that decide where a run's files land always travel
together and always mean the same thing, so they are one object rather
than three parameters threaded through every call - which also brought
`run_document_pipeline` back under this project's three-argument limit.

## path_for

Every filename is `{slug}_{name}_{timestamp}.{extension}`, built here and
nowhere else. Two consequences worth stating:

- The master document links to its siblings with `Path(path).name`, so
  its relative links only resolve because every document lands in the
  same directory with a name derived the same way.
- The JSON export's filename changed from `_graph_` to `_export_` when
  this landed. The name now comes from the registry key (`"export"`),
  which is also its config name and manifest key - the alternative was a
  fourth spelling of the same document maintained by hand. Only the
  on-disk name changed; `export_path` in the manifest and the docs index
  are unaffected, since both read the path rather than reconstructing it.

## _with_banner

The coverage banner is prepended here rather than inside each generator so
the rule exists once and a new document inherits it by existing.

Reads `request.coverage`, computed once by `run_document_pipeline` before
any generator runs - not a fresh `build_coverage` query per document,
which is what "computed once per run" (docs/adr/0001) actually asks for.

Skipped for anything but a `kind="view"`, `extension="md"` output, which
is not a stylistic choice: a JSON or YAML file with a Markdown blockquote
glued to the front no longer parses, and a `kind="source"` Markdown file
(hypothetically) reads as data, not as something a banner introduces. The
gate is kind **and** extension, not extension alone.

## _write_document

Builds every file one generator's `outputs()` declares and writes each to
disk - the one place `naming.path_for` is actually called, so every
`ProducedDocument` in the run went through the identical path-building
and checksum computation regardless of which generator produced it. A
multi-output generator (`coverage`, `export`) produces more than one
`ProducedDocument` from a single call here; a legacy single-string
generator produces exactly one, via `outputs()`'s own auto-wrap
(`core/documents.md#outputs`).

`checksum` is `sha256` of the bytes actually written - after
`_with_banner`, not before - so it verifies what a reader opening the
file on disk actually gets, not what the generator returned before the
pipeline modified it.

`relative_link` is `path` relative to `naming.out_dir`, forward slashes
forced regardless of host OS (it's a Markdown link, not a filesystem
path). Computed here because this is the one place `path` and
`naming.out_dir` are both in scope together - `master_document.py`'s
own renderers never see `naming` at all.

## run_document_pipeline

Computes `CrawlCoverage` exactly once, here, before the generator loop -
not per document. `coverage`'s own generator and every Markdown
document's banner both read `request.coverage` instead of each running
their own `build_coverage` query, which is what "computed once per run"
(docs/adr/0001) requires and what an earlier version of this pipeline did
not do.

**Why a failing generator is caught, not raised.** A crawl can take
twenty minutes. Losing every document because the ninth one hit an
unexpected shape in the graph would throw away the other eight, and the
run cannot be cheaply retried. This is the same "degrade this one output,
keep the rest" discipline `GraphPRDSynthesizer` already applies per page
and per batch.

The failed document is left out of `produced` rather than recorded as
empty, which is what stops the master document from linking to a file
that was never written - a dead link in the index would be a worse
failure mode than a missing entry, because it looks fine until clicked.

**Why the master document is constructed here rather than resolved from
the registry**: it is not an optional document a user turns on, it is the
pipeline's closing step, and it is the only generator whose input is the
other generators' output. See `master_document.md#masterdocument`.
