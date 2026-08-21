# `generators/asyncapi.py`

## module

`asyncapi.json` - locked ready for WS/SSE/long-polling traffic no
instrumentation observes yet, docs/adr/0018.

**Why `generate` raises instead of returning something.** ADR-0018 point
3 is explicit: there is no partial document worth reserving a field on,
unlike `evidence-log`'s `screenshot:` (ADR-0017, real data for two of
three kinds today). `run_document_pipeline`'s own "a generator that fails
is logged and skipped" degradation is what turns that raise into
`manifest.json`'s honest `status: "off"` - no second on/off mechanism
needed, matching the ADR's own point 3.

## ChannelObservation

## MessageObservation

Both synthetic today - no store method produces either, since no WS/SSE/
long-polling capture instrumentation exists. Exist so `channel_id`/
`message_id`/`build_asyncapi_document` are real, callable, unit-testable
functions rather than a design only written down in prose.

## channel_id

`CH-<hash>`, its own Short hash family member - deliberately not
`EP-<hash>`. ADR-0013 defined `EP-<hash>` narrowly as `method + host +
path_pattern`; a WebSocket channel has no HTTP method, and reusing `EP-`
here would quietly widen what it means for every existing citation.

## message_id

Hashes channel address + message name, not message name alone - the same
message name can mean something different on two different channels.

## _channel_bindings

AsyncAPI's real `ws` binding for a genuine WebSocket channel. `http` plus
`x-sse-stream`/`x-long-polling` for the two traffic shapes the spec's own
bindings catalog has no first-class binding for at all (ADR-0018 point
4, confirmed against the bindings repo directly, not assumed).

## _message_inference

The `x-inference` extension (ADR-0018 point 2) - AsyncAPI has no native
metadata hook beyond `x-` vendor extensions either, so this reuses
`openapi.py`'s exact `x-inference` pattern (ADR-0004) rather than
inventing a second one. Confidence scaling reuses `openapi.py`'s own
`_CONFIDENCE_CEILING_OBSERVATIONS` value - not HTTP-specific, so no
reason to pick a different number here.

## build_asyncapi_document

Real and callable, but **not wired to `AsyncAPIDocument.generate` today**
- there is no store method to call it with, since nothing captures a
`ChannelObservation`/`MessageObservation` yet. Whichever future ticket
adds detection instrumentation wires this function to a real store read;
this ticket's job was proving the function itself is correct.

## AsyncAPIDocument

Registered under `"asyncapi"` so `DOCUMENT_REGISTRY.names()` - and
therefore `manifest.json`'s own enumeration (`generators/master_document.py`)
- includes it. Deliberately absent from `core/config.py`'s default
`documents` list, so a normal run never even attempts it; a config that
explicitly adds `"asyncapi"` still gets a clean `status: "off"` rather
than a cryptic `AttributeError`, because `generate` raises a real,
explanatory error instead of reaching for a store method that doesn't
exist.
