# spiders/content/redaction.py

## module

Strips credentials and PII from captured network bodies and headers **before
they reach storage**.

**Why capture time and not read time.** Once a secret is written to storage it
has already leaked - the `.lbdb` is a file on disk, it gets copied, and every
document generated from it is downstream. There is no "redact on the way out"
that undoes an unredacted write. So this runs in `network_filter`, between the
browser and the graph.

This pipeline also feeds LLM prompts. A captured `Authorization` header or a
`password` field left in a request body would sit inside one.

### Two independent layers, applied together

1. **Key-based**, JSON bodies only: a value whose own key name looks sensitive
   (`password`, `token`, `api_key`, ...) is dropped outright regardless of its
   shape. This is the reliable, low-false-positive layer, because it acts on
   something the payload's own author named.
2. **Pattern-based**, every string whether JSON or not: emails, card-like digit
   runs, and long token/JWT-shaped strings are redacted wherever they appear -
   including inside a value whose key gave no hint at all.

`Authorization`, `Cookie` and `Set-Cookie` header values are dropped whole
rather than scanned, since there is no case where their content is wanted.

**Over-redaction is the correct failure mode.** A false positive costs a little
information in a document; a false negative leaks a secret into a file and every
prompt built from it. The patterns are deliberately broad for that reason, and a
redacted field still shows its key, so a reader can see that something was
there.

### What this makes possible downstream

The reason it matters beyond hygiene: because bodies arrive redacted, they can be
**published**. `InferredRequest.request_example`/`response_example` and the
OpenAPI `example` blocks exist because of this module - the earlier design
persisted only type-shapes precisely because nothing scrubbed the values. See
`docs/dev/database/ladybug/network.md#get_inferred_requests`, and note the
end-to-end verification recorded there rather than trusting unit tests alone.

Two tests in the suite once asserted "body text must never survive". They
encoded the *old* design and were rewritten deliberately when this landed - a
distinction worth keeping in mind before making a failing redaction test pass.
