# `interactive/customization.py`

## module

ADR-0031's "effective document" lookup and customized-document writer - the one place every
consumer of a site's documents (the interactive dashboard's editor, its future chat) resolves a
document's current content through, so `customized/` vs. the original crawl output is never a
per-caller decision.

**Filenames, not `runs.json`.** A site's real produced files are found by globbing `{slug}_*`
under `out_dir` directly, never by trusting `runs.json`'s own `document_paths` - that dict is
keyed by `DocumentGenerator.name` (the registry key), and a multi-output generator (`tokens`,
`flows`, ...) writes several `ProducedDocument`s sharing one `name` but different
`filename`/`extension`, so `document_paths` silently keeps only whichever one iterated last (a
known gap, noted as fog on map #94 before this ticket - not fixed here, just not relied on).
`(filename, extension)` is the real, collision-free identity of one physical file
`generators/pipeline.py::DocumentNaming.path_for` writes.

**Customized files are flat, not per-site subdirectories.** Matches `DocumentNaming`'s own
`{slug}_{filename}_{timestamp}.{extension}` convention minus the timestamp (a customized document
isn't a per-run artifact) - see ADR-0031's own "Update" callout for why this differs from what
that ADR originally said before this ticket implemented it.

## SCHEMA_PATH_BY_FILENAME

One entry per produced-document filename that has a real vendored JSON Schema
(`utils/schema_validation.py`) - built by grepping every generator's own `_SCHEMA_PATH` constant
and its matching `DocumentOutput(filename=...)` call, not guessed. Absent here means "no known
schema" - a customized copy still gets written, just without a validation gate. `openapi.yaml` is
deliberately absent: it validates through `openapi-spec-validator`, a dedicated OpenAPI validator,
not the generic `jsonschema`-based one this table serves.

`tests/test_interactive_customization.py::test_every_schema_path_in_the_table_points_at_a_real_file`
checks every path actually resolves - a typo here would silently disable validation for that one
document with no error anywhere.

## SiteOutput

`out_dir` + `site`, the pair every function in this module needs - bundled per
`python-clean-code`'s F1 (max 3 args) rather than threaded through each signature separately. A
real fix, not a stylistic one: the first draft of this module had `_original_path`/`customized_
path`/`effective_content` at 4 args and `save_customized` at 5, caught during this ticket's own
quality pass.

## DocumentRef

`(filename, extension)` - what `available_documents`/`effective_content`/`save_customized` key by,
not the registry `name` a multi-output generator shares across several real files.

## available_documents

Globs `{slug}_*`, parses each match's own `{filename}_{timestamp}.{extension}` tail via
`_PRODUCED_FILENAME`, and dedupes down to the distinct `(filename, extension)` pairs found - the
newest run's own document set, since a stale earlier run's files share the same filename/extension
and just get overwritten in the dedup dict.

## _original_path

The most recent original file for `(filename, extension)`, or `None` if this site never produced
one. Sorted lexicographically, which sorts correctly by time too since the embedded timestamp is
`YYYYMMDDTHHMMSSZ`.

## customized_path

Always the same path for a given `(site, filename, extension)` - overwritten in place on every
save, never one file per edit (ADR-0031 point 2's own "always the latest state, never a version
history").

## effective_content

The customized copy if one exists, else the original - ADR-0031's own read-time-resolution rule,
in one place so no caller re-derives it. `None` when neither exists (nothing was ever produced for
this `(filename, extension)`).

## schema_path_for

`SCHEMA_PATH_BY_FILENAME.get(filename)` - `None` for a document this table hasn't been extended
for, or that validates a different way entirely (`openapi.yaml`'s own OpenAPI-spec validator).

## _parse_for_validation

The shape `jsonschema.validate` needs `content` in - `.yaml` parses as one document
(`tree.aria.yaml`), `.jsonl` parses as an array of its own lines (the schema validates the row
list, not the newline-delimited file on disk - `generators/evidence_log.py`'s own module docstring
says so), everything else as one JSON document.

## save_customized

Validates against `schema_path_for(filename)` first when one exists, then writes - a customized
document is always schema-valid by construction (ADR-0031 point 2), never a drifting override that
could silently stop matching its own schema. Raises `jsonschema.ValidationError` or a parse error
on invalid input; the caller (the Flask route in `interactive/server.py`) turns that into a real
response, this function doesn't catch it itself.
