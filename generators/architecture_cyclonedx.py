"""`architecture.cyclonedx.json`: the third-party integration inventory,
per docs/adr/0010 point 2. CycloneDX 1.6's `externalServices` construct -
purpose-built for an *observed service dependency*, which is what
pragma's traffic-domain analysis actually detects, unlike SPDX's
installed-package-provenance model.

Reads directly off `Endpoint` nodes where `first_party = false`
(`GraphStore.integrations()`), the same call `export.json`'s own
`Endpoint` population makes - not a second, independently-detected
inventory (ADR-0010 point 4).

Details: docs/dev/generators/architecture_cyclonedx.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

_SPEC_VERSION = "1.6"
_BOM_FORMAT = "CycloneDX"

# CycloneDX's externalServices.properties is a flat {name, value} array
# (its `additionalProperties: false` sanctioned extension point, unlike
# CALM's free-form metadata) - `pragma` is registered as a top-level
# namespace in the upstream cyclonedx-property-taxonomy, colon-delimited
# per that taxonomy's own convention (ADR-0010 point 7).
_PROPERTY_SOURCE = "pragma:evidence:source"
_PROPERTY_OBSERVATION_COUNT = "pragma:evidence:observationCount"
_PROPERTY_HAR_REQUEST_ID = "pragma:evidence:harRequestId"


def hosts_by_traffic(integrations: Sequence[Dict[str, Any]]) -> List[Tuple[str, int, int]]:
    """`[(host, calls, endpoint_count)]`, busiest first.

    `GraphStore.integrations()` returns one row per third-party endpoint;
    a reader (and a BOM) wants one service per vendor. Which services
    this application depends on is asked per host, not per URL.
    Details: docs/dev/generators/architecture_cyclonedx.md#hosts_by_traffic
    """
    totals: Dict[str, List[int]] = {}
    for endpoint in integrations:
        entry = totals.setdefault(endpoint.get("host") or "(unknown host)", [0, 0])
        entry[0] += endpoint.get("call_count") or 0
        entry[1] += 1
    return sorted(
        ((host, calls, endpoints) for host, (calls, endpoints) in totals.items()),
        key=lambda row: (-row[1], -row[2], row[0]),
    )


def _external_service(host: str, calls: int, endpoint_count: int) -> Dict[str, Any]:
    return {
        "provider": {"name": host},
        "endpoint": [f"https://{host}"],
        "name": host,
        "description": f"{endpoint_count} distinct endpoint(s) observed, {calls} call(s) total.",
        "properties": [
            {"name": _PROPERTY_SOURCE, "value": "network-traffic-analysis"},
            {"name": _PROPERTY_OBSERVATION_COUNT, "value": str(calls)},
            # Reserved: this crawl captures no HAR entries with a stable
            # per-request id yet (docs/adr/0001's reserved-field pattern).
            {"name": _PROPERTY_HAR_REQUEST_ID, "value": ""},
        ],
    }


def build_cyclonedx_document(integrations: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The full `architecture.cyclonedx.json` payload: one `externalServices`
    entry per distinct third-party host.
    Details: docs/dev/generators/architecture_cyclonedx.md#build_cyclonedx_document
    """
    return {
        "bomFormat": _BOM_FORMAT,
        "specVersion": _SPEC_VERSION,
        "version": 1,
        "externalServices": [
            _external_service(host, calls, endpoints) for host, calls, endpoints in hosts_by_traffic(integrations)
        ],
    }
