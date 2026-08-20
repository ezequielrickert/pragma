# `redaction-log` consolidates after the fact; it's never itself redactable

**Status**: accepted

The ticket's first open point resolves on a spec-conformance fact: the OpenAPI Overlay Specification
`openapi` already adopted (ADR-0004) is conformance-scoped to OpenAPI documents specifically — it
requires an `extends` field targeting an OpenAPI document — so it can't be mandated as a universal
redaction mechanism for CALM, EARL, SARIF, or `tokens.json` without violating the spec it claims to
follow. The other two points resolve from that same principle.

Decided, resolving the ticket's three open points:

**1. Consolidation, Not a Universal Mechanism.** `redaction-log` indexes redaction events *after the
fact* from whichever documents already redact, by whatever document-appropriate mechanism each one
uses — `openapi`'s raw-private/Overlay/public split today, a future document's own choice when it
needs one. What generalizes is the *principle* (a raw private artifact, a record of what changed, a
public artifact), not the Overlay Specification itself.

**2. Schema: JSONL, No Per-Entry ID.** Matches `evidence-log`'s established event-log shape
(ADR-0017) — append-only, one row per redaction event: `source_document`, `field_path` (a JSONPath,
generic across any JSON-shaped document, not OpenAPI-specific), `reason` (citing `data-model`'s DPV
categories where applicable — `is_pii`/`dpv_type`, ADR-0008 — or a legal/business reason otherwise),
`run_id`, and evidence that redaction happened (the raw-private and public artifacts both existing —
never the redacted value itself). No Short hash ID: nothing currently needs to cite a specific
redaction event by reference, and inventing one on spec would be scope nothing asked for.

**3. Not Itself Redactable, By Construction.** Every field in a `redaction-log` entry describes
*metadata about* a redaction — which field, which document, why — and never touches the underlying
secret value, the same posture as any audit log. There's nothing in it that needs hiding because it
never contains what it records the removal of, and the document's entire value depends on a reviewer
being able to read it freely to verify redaction actually happened. No access-control layer needed;
the schema itself makes the question moot.

Depends on `openapi`'s Overlay redaction workflow (ADR-0004).

Wayfinder ticket: [redaction-log: consolidate redaction events across documents](https://github.com/ezequielrickert/pragma/issues/85),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
