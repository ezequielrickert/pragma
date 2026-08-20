# `asyncapi` locks a format ready for traffic no instrumentation observes yet

**Status**: accepted

The ticket asks for `asyncapi`'s contract to be ready the moment a crawl needs it, conditional on
whether message-based traffic (WebSockets, SSE, long-polling) is even observed. Checking the
codebase: zero instrumentation for any of the three exists today, the same situation `evidence-log`
found for screenshot capture (ADR-0017) — except here nothing is real yet, not just one kind among
several. AsyncAPI 3.0 research surfaced one structural wrinkle worth locking explicitly: its
`operationId`/`messageId` are map keys, not object fields, unlike OpenAPI's `operationId`.

Decided, resolving the ticket's three open points:

**1. Channel/Message ID Scheme.** Two new members of the **Short hash** family (`CONTEXT.md`,
`sha1(...)[:10]`): `CH-<hash>` (a channel — hash of protocol + host + channel address) and
`MSG-<hash>` (a message — hash of channel address + message name), used as the map keys AsyncAPI
3.0's `Operations`/`Messages` objects require (confirmed: `operationId`/`messageId` are the map key
itself, not a field on the object — different from OpenAPI, where `operationId` *is* a field, so
`generators/openapi.py`'s CRUD-verb `_operation_id` pattern doesn't transfer here anyway; a
WebSocket channel has no HTTP method to build a verb from). Distinct prefixes from `EP-<hash>`,
which ADR-0013 defined narrowly as `method + host + path_pattern` — reusing it would quietly widen
what `EP-` means.

**2. Evidence and Provenance.** AsyncAPI 3.0 has no native metadata hook beyond `x-` vendor
extensions (confirmed against the spec's JSON Schema — every object's only extension point is
`patternProperties` on `^x-`, identical in shape to OpenAPI's). Reuses `openapi`'s exact pattern
(ADR-0004): `x-inference` for observation counts and confidence, evidence pointers in the same
`interaction:<id>`/`har:<id>` convention every other document in this map already emits.

**3. Presence and Detection.** `asyncapi.json` is entirely **absent** — no file, not even
empty-but-valid — until WebSocket/SSE/long-polling capture instrumentation exists. This differs from
`evidence-log`'s reserved-kind approach (ADR-0017): `evidence-log` has real data today for two of
its three kinds, so a reserved placeholder for the third makes sense; `asyncapi` has nothing real to
report for any of it yet, so there's no partial document to reserve a field on. Presence is governed
by `manifest.json`'s existing `status` field (ADR-0015) — no new on/off mechanism needed.

**4. SSE and Long-Polling Representation.** AsyncAPI's official bindings catalog has a first-class
`ws` binding but no SSE or long-polling binding at all (confirmed against the bindings repo — the
spec is silent on both). Both are modeled under the generic `http` binding plus custom
`x-sse-stream`/`x-long-polling` extension flags describing the streaming/polling behavior, kept in
`asyncapi.json` per the ticket's own scope framing — not split into `openapi.yaml` on the technicality
that an SSE connection's handshake is a normal HTTP GET. One traffic pattern stays one document.

Wayfinder ticket: [asyncapi: lock contract for WebSocket/SSE/long-polling traffic](https://github.com/ezequielrickert/pragma/issues/82),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
