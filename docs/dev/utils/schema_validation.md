# `utils/schema_validation.py`

## module

The one shared entry point every source-document generator calls before
writing its output - CALM, CycloneDX, SARIF, AsyncAPI, OpenAPI,
ACT Rules, Custom Elements Manifest, and DTCG all publish an official
JSON Schema (confirmed while charting docs/adr/0001-0029), so one
generic validator covers nearly every format this pipeline emits.

`data` is typed `Any`, not `Dict`: most of this pipeline's documents are
JSON objects at the root, but `tree.aria.schema.json` (docs/adr/0003) is
an array, so the parameter stays as loose as the schemas it validates
against actually are. Raises `jsonschema.ValidationError` on a mismatch
rather than returning a boolean - a caller that wants one catches it
itself, rather than this function swallowing the detail into a bare
`True`/`False`.
