# `generators/openapi_lint.py`

## module

A local stand-in for docs/adr/0004's vacuum/Spectral ruleset. This repo
has no Node.js toolchain and no CI to run either linter in (confirmed
while implementing ticket #99: no `package.json`, no `.github/workflows`
anywhere in the tree) - wiring vacuum or Spectral is real, separate
infrastructure work outside what a `DocumentGenerator` ticket covers, a
follow-up ticket's job if the map wants it formally, not something faked
here.

What this module actually enforces, in plain Python, matching the base
ruleset ADR-0004 names: `operation-operationId-unique`,
`path-declarations-must-exist`, `operation-success-response`, plus
pragma's own custom rule (the `x-inference` extension's presence and
shape, checked against `schemas/openapi.x-inference.schema.json`).
`oas3-schema` itself is `openapi_spec_validator.validate`, called in
`generators/openapi.py` before this module ever runs - a real schema, not
reimplemented here.

Findings are printed, not raised: a finding like "this operation never
observed a 2xx response" describes what the crawl found, not a bug in
this generator - blocking document generation on it would be exactly the
kind of invented certainty docs/adr/0001's reserved-field discipline
exists to avoid elsewhere in this pipeline.

## lint_openapi_document

Runs every check and concatenates their findings, empty when clean. The
one entry point `generators/openapi.py::OpenAPIDocument.generate` calls,
against the public document (the one a reader actually sees), not the
raw one.
