# `utils/jsonl.py`

## module

One JSON object per line, sorted keys - the shared serializer behind
every per-run event-log document (`evidence-log.jsonl`, ADR-0017;
`redaction-log.jsonl`, ADR-0021). Extracted once a second identical
two-line implementation appeared; never reimplemented per document from
here on.

## as_jsonl

Pure formatting, no validation - each caller schema-validates `rows`
itself (against its own document's schema) before calling this.
