# `generators/redaction_log.py`

## module

`redaction-log.jsonl` - consolidates redaction events across documents
after the fact, docs/adr/0021. `openapi`'s OpenAPI Overlay workflow
(ADR-0004) is the only real source in v1; a future document that needs
redaction picks its own document-appropriate mechanism and gets indexed
here the same way once it does.

**Why only the Overlay layer.** `openapi.raw.yaml` already reflects
capture-time redaction (`spiders/content/redaction.py`) before this
module ever sees it, and that pass has no structured target/action
record - there's nothing to cite a `field_path` from. Only the Overlay's
own hand-authored, structured rules are indexable.

**Why one row per concrete field, not per rule.** A wildcard target like
`$.paths[*][*].example` is one *rule*, but redacts several distinct
fields - each gets its own row, citing the concrete path it actually
matched. A rule that matches nothing this run contributes no row: an
unfired rule isn't evidence anything was redacted.

## build_redaction_log

Recomputes `openapi.raw.yaml`'s own document directly from the graph
(`openapi.build_openapi_document`, deterministic, no model call) rather
than reading a file `openapi`'s own generator may not have written this
run - the same "call the real build function" discipline every
cross-generator call in this map already follows.

## RedactionLogDocument

Source only, no view - the same shape `evidence-log` already settled on
for a per-run audit-trail file read as rows, not prose.
