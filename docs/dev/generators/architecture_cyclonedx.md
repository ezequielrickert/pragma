# `generators/architecture_cyclonedx.py`

## module

`architecture.cyclonedx.json`: the third-party integration inventory,
per docs/adr/0010 point 2. CycloneDX 1.6's `externalServices` construct -
purpose-built for an *observed service dependency*, which is what
pragma's traffic-domain analysis actually detects, unlike SPDX's
installed-package-provenance model.

Reads directly off `Endpoint` nodes where `first_party = false`
(`GraphStore.integrations()`), the same call `export.json`'s own
`Endpoint` population makes - not a second, independently-detected
inventory (ADR-0010 point 4).

## hosts_by_traffic

`GraphStore.integrations()` returns one row per third-party endpoint; a
BOM wants one service per vendor. Moved here from the retired
`generators/architecture_map.py` verbatim - the aggregation logic didn't
change, only its consumer (a CycloneDX `externalService` instead of a
Markdown table row).

## build_cyclonedx_document

One `externalServices` entry per distinct host. `pragma:evidence:source`
and `pragma:evidence:observationCount` are real; `pragma:evidence:
harRequestId` is reserved - this crawl captures no HAR entries with a
stable per-request id yet (docs/adr/0001's reserved-field pattern,
applied to a CycloneDX property instead of a JSON field).
