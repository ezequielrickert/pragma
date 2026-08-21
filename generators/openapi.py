"""D4: an OpenAPI 3.1 contract inferred from the traffic a crawl observed,
per docs/adr/0004.

Entirely deterministic - no model call anywhere. Everything here is a
rearrangement of what `GraphStore.get_inferred_requests` already grouped
(computed on read from the graph's `Request`/`Endpoint` nodes, not a
rebuild pass this module triggers), which is why the output can be
trusted as a contract rather than read as a summary.

**Examples are real bodies, and that is the one place this document
carries captured data rather than derived shapes.** They pass through two
layers of redaction. The first runs at capture time and is not optional
(`spiders/content/redaction.py`: fields named like secrets dropped by
name, every string pattern-scanned for emails, card-like digit runs and
tokens, `Authorization`/`Cookie` dropped whole) - `openapi.raw.yaml`
already reflects it, "raw" here means "before the second, document-level
pass," never "before any redaction at all." The second is the
OpenAPI Overlay (`generators/openapi_overlay.py`,
`config/redaction.overlay.yaml`, ADR-0004's non-destructive workflow): a
hand-maintained rule set a maintainer extends for whatever the first pass
missed, applied to produce the public `openapi.yaml`. A response example
is only ever taken from a call that answered 2xx - a 422's body describes
the error shape, and publishing it as the endpoint's response would
misdescribe the API.

What it still cannot contain, by construction rather than oversight: field
constraints (enum, pattern, minimum), which need many values per field to
infer and would be guesses from one; and any endpoint the crawl never
reached. The generated document says so in its own description rather than
looking complete.

Details: docs/dev/generators/openapi.md#module
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import yaml
from openapi_spec_validator import validate as validate_openapi

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.interfaces import InferredRequest
from core.registry import DOCUMENT_REGISTRY
from .json_schema import schema_from_shape
from .openapi_lint import lint_openapi_document
from .openapi_overlay import apply_overlay

_OVERLAY_PATH = "config/redaction.overlay.yaml"
_EMPTY_OVERLAY = {"overlay": "1.0.0", "info": {"title": "Pragma redaction overlay", "version": "1.0.0"}, "actions": []}
# The exact filenames generate() writes below - named so redaction_log.py
# can cite which artifact backs its own evidence without duplicating the
# literal strings (docs/adr/0021 point 2's "evidence that redaction
# happened" is the raw-private and public artifacts both existing).
RAW_FILENAME = "openapi.raw"
PUBLIC_FILENAME = "openapi"
# One observation is not enough to trust a generalization; five
# independent calls to the same operation is - a deliberately simple,
# stated v1 heuristic, not a statistical model.
# Details: docs/dev/generators/openapi.md#_confidence_ceiling
_CONFIDENCE_CEILING_OBSERVATIONS = 5

# HTTP method -> the CRUD verb an operationId/summary is built from. GET is
# absent on purpose: it means "list" or "get" depending on whether the call
# carries query parameters. Details: docs/dev/generators/openapi.md#_crud_verbs
_CRUD_VERBS = {"POST": "create", "PUT": "replace", "PATCH": "update", "DELETE": "delete"}

_CONTRACT_PREAMBLE = (
    "Inferred from traffic observed during an automated crawl, not from server source. Security "
    "schemes are named from request header names only - never from a credential - so this says "
    "which scheme an endpoint uses and never what the token was. Examples are real captured "
    "bodies, redacted (secret-named fields dropped, emails/card-like numbers/tokens scrubbed) and "
    "truncated; each is one observation rather than a canonical payload, and a response example "
    "is only ever taken from a call that answered 2xx. Field constraints (enum, pattern, minimum) "
    "are absent by design: inferring them needs many values per field, and from one observation "
    "they would be guesses. Endpoints the crawl never reached are absent too - see the crawl "
    "coverage document."
)


def _security_scheme(scheme: str) -> Tuple[str, Dict[str, Any]]:
    """One observed scheme as an OpenAPI `securitySchemes` entry.

    Args:
        scheme: what `network_filter._auth_scheme` reported - `"bearer"`,
            `"basic"`, `"cookie"`, or `"header:x-api-key"`.

    Returns:
        `(name, definition)`. Anything unrecognised becomes an `http`
        scheme under its own name rather than being dropped: an
        unfamiliar `Authorization` scheme is still authentication, and
        omitting it would tell a reader the endpoint is open.
    Details: docs/dev/generators/openapi.md#_security_scheme
    """
    if scheme.startswith("header:"):
        header = scheme.split(":", 1)[1]
        name = _camel(header)
        # `x-api-key` already ends in "key"; appending another reads as a typo.
        return (name if name.lower().endswith("key") else name + "Key"), {
            "type": "apiKey", "in": "header", "name": header,
        }
    if scheme == "cookie":
        return "sessionCookie", {"type": "apiKey", "in": "cookie", "name": "session"}
    if scheme in ("bearer", "basic"):
        return f"{scheme}Auth", {"type": "http", "scheme": scheme}
    return f"{_camel(scheme)}Auth", {"type": "http", "scheme": scheme}


def _camel(value: str) -> str:
    parts = [part for part in value.replace("_", "-").split("-") if part]
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:]) if parts else "auth"


def _host_and_path(endpoint: str) -> Tuple[str, str]:
    """Split `"api.x.com/rest/v1/orders"` into its host and `/`-prefixed path."""
    host, _, path = endpoint.partition("/")
    return host, "/" + path


def _singular(segment: str) -> str:
    """`"orders"` -> `"order"`, for naming a path parameter after what it
    identifies. Deliberately naive: this names a parameter, and `{itemId}`
    beats `{id}` even when the singular form is imperfect."""
    return segment[:-1] if len(segment) > 3 and segment.endswith("s") else segment


def path_template(path: str) -> Tuple[str, List[str]]:
    """Rename each `{id}` after the segment before it, and list the results.

    `database/ladybug/network.py::_pattern_and_params` collapses every
    opaque segment to the same `{id}`, which is fine as a grouping key
    and invalid as an OpenAPI path:
    `/orders/{id}/items/{id}` declares one parameter name twice. Naming
    each after its preceding segment fixes that and reads better.

    Args:
        path: a `/`-prefixed path, e.g. `"/orders/{id}/items/{id}"`.

    Returns:
        `("/orders/{orderId}/items/{itemId}", ["orderId", "itemId"])`. A
        name that would still collide gets a numeric suffix, so the result
        is always a valid OpenAPI path.
    Details: docs/dev/generators/openapi.md#path_template
    """
    segments = path.split("/")
    names: List[str] = []
    for index, segment in enumerate(segments):
        if segment != "{id}":
            continue
        previous = segments[index - 1] if index > 0 else ""
        name = f"{_singular(previous)}Id" if previous else "id"
        if name in names:
            name = f"{name}{names.count(name) + 1}"
        names.append(name)
        segments[index] = f"{{{name}}}"
    return "/".join(segments), names


def _capitalized(word: str) -> str:
    return f"{word[:1].upper()}{word[1:]}"


def _verb_and_subject(request: InferredRequest, resource: str) -> Tuple[str, str]:
    """The CRUD verb this operation performs and what it performs it on.

    Plural only for a listing, singular everywhere else: `POST /orders`
    creates one order, and `createOrders` would claim otherwise. This ends
    up in generated client code, so the number is worth getting right even
    though nothing validates it.
    """
    verb = _CRUD_VERBS.get(request.method) or ("list" if request.query_params else "get")
    return verb, resource if verb == "list" else _singular(resource)


def _operation_id(request: InferredRequest, resource: str) -> str:
    """`createOrder`, `listOrders`, `deleteOrder`."""
    verb, subject = _verb_and_subject(request, resource)
    return f"{verb}{_capitalized(subject)}"


def operation_id_for(request: InferredRequest) -> str:
    """The real `operationId` `build_openapi_document` would mint for this
    request, derived the identical way (`_resource_name` off the same
    `_host_and_path` split). Public so `generators/flows.py`'s Arazzo
    workflow steps (ADR-0014 point 1) can cite the exact id
    `openapi.yaml` itself carries, rather than re-deriving the naming
    formula independently and risking drift.
    Details: docs/dev/generators/openapi.md#operation_id_for
    """
    resource = _resource_name(_host_and_path(request.endpoint)[1])
    return _operation_id(request, resource)


def _summary(request: InferredRequest, resource: str) -> str:
    """`"List orders"`, `"Create item"` - a phrase, not a restatement.

    An earlier version repeated the operationId and the raw endpoint,
    which also showed `{id}` while the path key above it showed
    `{orderId}` - the same parameter under two names, one line apart.
    """
    verb, subject = _verb_and_subject(request, resource)
    return f"{_capitalized(verb)} {subject}"


def _resource_name(path: str) -> str:
    """The last segment that isn't a path parameter - what the operation acts on."""
    concrete = [seg for seg in path.split("/") if seg and not seg.startswith("{")]
    return concrete[-1] if concrete else "root"


def _observed_description(request: InferredRequest) -> str:
    """Where this endpoint was seen from, in one prose block.

    The traceability is the point: a reader who doubts an operation can go
    straight to the control or page it was observed from, rather than
    taking the document's word for it.
    """
    lines = []
    if request.triggered_by:
        controls = ", ".join(f"`{path}` on `{page}`" for page, path in request.triggered_by[:5])
        lines.append(f"Triggered by: {controls}.")
    if request.loaded_by:
        lines.append(f"Fired on page load of: {', '.join(request.loaded_by[:5])}.")
    if request.latencies_ms:
        lines.append(
            f"Observed latency: {min(request.latencies_ms)}-{max(request.latencies_ms)} ms "
            "(measured through the crawl's own browser; relative signal, not a performance figure)."
        )
    return " ".join(lines)


class _SchemaRegistry:
    """Collects response/request schemas, deduplicating identical ones into
    `components/schemas` so a shape shared by several operations is written
    once and referenced.
    Details: docs/dev/generators/openapi.md#_schemaregistry
    """

    def __init__(self) -> None:
        self._by_key: Dict[str, str] = {}
        self.schemas: Dict[str, Dict[str, Any]] = {}

    def reference(self, schema: Dict[str, Any], preferred_name: str) -> Dict[str, Any]:
        """A `$ref` to `schema`, registering it first if it's new.
        Trivial schemas (no properties to speak of) are returned inline -
        a named component for `{}` costs a lookup and explains nothing.
        """
        if not schema or not schema.get("properties"):
            return schema
        key = yaml.safe_dump(schema, sort_keys=True)
        if key not in self._by_key:
            name = preferred_name
            suffix = 2
            while name in self.schemas:
                name = f"{preferred_name}{suffix}"
                suffix += 1
            self._by_key[key] = name
            self.schemas[name] = schema
        return {"$ref": f"#/components/schemas/{self._by_key[key]}"}


def _responses(request: InferredRequest, schemas: _SchemaRegistry, resource: str) -> Dict[str, Any]:
    """One entry per status code actually observed, never a guessed 200."""
    response_schema = schema_from_shape(request.response_shape)
    if not request.status_codes:
        return {"default": {"description": "No response status was captured for this endpoint."}}

    # The media type the server actually answered with, rather than
    # assuming JSON for an endpoint that returns XML or a redirect.
    # Details: docs/dev/generators/openapi.md#media-types
    media_type = request.media_types[0] if request.media_types else "application/json"
    responses: Dict[str, Any] = {}
    for code in request.status_codes:
        entry: Dict[str, Any] = {"description": f"Observed response (HTTP {code})."}
        if 200 <= code < 300 and response_schema:
            body: Dict[str, Any] = {
                "schema": schemas.reference(response_schema, f"{_capitalized(_singular(resource))}Response")
            }
            # Already restricted to successful calls upstream, so it belongs
            # on exactly the codes that carry a schema.
            if request.response_example:
                body["example"] = request.response_example
            entry["content"] = {media_type: body}
        responses[str(code)] = entry
    return responses


def _confidence(request: InferredRequest, has_data: bool) -> float:
    """How much this operation's observation count backs one inferred
    aspect (a path template, a body shape) - `0.0` when there is no data
    to be confident in at all, otherwise scaling toward `1.0` as more
    independent calls confirmed the same shape.
    Details: docs/dev/generators/openapi.md#_confidence
    """
    if not has_data:
        return 0.0
    return round(min(1.0, request.observation_count / _CONFIDENCE_CEILING_OBSERVATIONS), 2)


def _inference(request: InferredRequest, path_param_names: List[str]) -> Dict[str, Any]:
    """The `x-inference` extension (docs/adr/0004): observed versus
    inferred, with a confidence per inferred aspect.

    `methods_inferred` is always `[]` in v1 - this crawler infers a
    path's *shape* (opaque segments generalized to `{id}`) and a body's
    *structure* from observed samples, but never an HTTP method nobody
    ever actually called; inventing "PUT is probably also supported"
    would be exactly the guess this document's own preamble disclaims.

    `path_params` confidence is `1.0` when the path carries none - a
    verified structural fact (zero opaque segments found), not a guess -
    and observation-scaled otherwise, since a single hit generalizing an
    id segment could in principle be a coincidence.
    Details: docs/dev/generators/openapi.md#_inference
    """
    return {
        "observation_count": request.observation_count,
        "methods_observed": [request.method],
        "methods_inferred": [],
        "confidence": {
            "path_params": 1.0 if not path_param_names else _confidence(request, True),
            "request_schema": _confidence(request, bool(request.body_shape)),
            "response_schema": _confidence(request, bool(request.response_shape)),
        },
    }


def _operation(request: InferredRequest, names: List[str], schemas: _SchemaRegistry) -> Dict[str, Any]:
    resource = _resource_name(_host_and_path(request.endpoint)[1])
    operation: Dict[str, Any] = {
        "operationId": _operation_id(request, resource),
        "summary": _summary(request, resource),
        "responses": _responses(request, schemas, resource),
        "x-inference": _inference(request, names),
    }
    description = _observed_description(request)
    if description:
        operation["description"] = description

    parameters = [
        {"name": name, "in": "path", "required": True, "schema": {"type": "string"}} for name in names
    ] + [
        {"name": name, "in": "query", "required": False, "schema": {"type": "string"}}
        for name in request.query_params
    ]
    if parameters:
        operation["parameters"] = parameters

    body_schema = schema_from_shape(request.body_shape)
    if body_schema:
        sent: Dict[str, Any] = {
            "schema": schemas.reference(body_schema, f"{_capitalized(_singular(resource))}Request")
        }
        if request.request_example:
            sent["example"] = request.request_example
        operation["requestBody"] = {"required": True, "content": {"application/json": sent}}
    return operation


def build_openapi_document(requests: List[InferredRequest], site: str) -> Dict[str, Any]:
    """Assemble one OpenAPI 3.1 document from already-inferred endpoints -
    `openapi.raw.yaml`'s content, before the redaction overlay.
    Details: docs/dev/generators/openapi.md#build_openapi_document
    """
    schemas = _SchemaRegistry()
    security_schemes: Dict[str, Dict[str, Any]] = {}
    paths: Dict[str, Dict[str, Any]] = {}
    hosts = sorted({_host_and_path(request.endpoint)[0] for request in requests})

    for request in sorted(requests, key=lambda r: (r.endpoint, r.method)):
        host, raw_path = _host_and_path(request.endpoint)
        templated, names = path_template(raw_path)
        item = paths.setdefault(templated, {})
        operation = _operation(request, names, schemas)
        for scheme in request.auth_schemes:
            name, definition = _security_scheme(scheme)
            security_schemes[name] = definition
            operation.setdefault("security", []).append({name: []})
        item[request.method.lower()] = operation
        # Per-path servers, so a crawl spanning several hosts stays
        # unambiguous instead of silently attributing every path to one.
        # Details: docs/dev/generators/openapi.md#per-path-servers
        if len(hosts) > 1:
            item["servers"] = [{"url": f"https://{host}"}]

    document: Dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": f"{site} - inferred API contract",
            "version": "0.1.0",
            "description": _CONTRACT_PREAMBLE,
        },
        "paths": paths,
    }
    if hosts:
        document["servers"] = [{"url": f"https://{host}"} for host in hosts]
    components: Dict[str, Any] = {}
    if schemas.schemas:
        components["schemas"] = schemas.schemas
    if security_schemes:
        components["securitySchemes"] = security_schemes
    if components:
        document["components"] = components
    return document


def load_overlay() -> Dict[str, Any]:
    """`config/redaction.overlay.yaml`, or the empty default when nobody
    has added one yet - a missing overlay file is a valid v1 state
    (capture-time redaction alone), not an error. Public: `redaction_log.py`
    calls this directly rather than re-reading the file itself, the same
    "call the real build function, never read files twice" discipline
    every other cross-generator call in this map already follows.
    Details: docs/dev/generators/openapi.md#load_overlay
    """
    try:
        with open(_OVERLAY_PATH, encoding="utf-8") as handle:
            return yaml.safe_load(handle) or _EMPTY_OVERLAY
    except FileNotFoundError:
        return _EMPTY_OVERLAY


def _as_yaml(document: Dict[str, Any]) -> str:
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True, default_flow_style=False)


@DOCUMENT_REGISTRY.register("openapi")
class OpenAPIDocument(DocumentGenerator):
    """Three files per docs/adr/0004's non-destructive redaction workflow:
    `openapi.raw.yaml` (private - everything this generator inferred,
    beyond the capture-time redaction that already ran), a copy of the
    `redaction.overlay.yaml` rules actually applied this run (provenance:
    which ruleset version produced the public file, without trusting a
    maybe-since-edited config file to still match), and the public
    `openapi.yaml` the overlay produces. All three are OpenAPI 3.1
    documents, validated against the real OpenAPI 3.1 schema before
    being written - the base `oas3-schema` rule ADR-0004 names. The rest
    of its named ruleset runs as `generators/openapi_lint.py`, printed as
    findings rather than a hard failure (see that module's own docstring
    for why there's no vacuum/Spectral/CI here).
    Details: docs/dev/generators/openapi.md#openapidocument
    """

    name = "openapi"
    title = "API Contract"
    purpose = (
        "Every endpoint the crawl observed, as an OpenAPI 3.1 spec (raw private, redaction overlay, "
        "and public variants) - feeds client generators and mock servers."
    )
    extension = "yaml"

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        requests = request.graph_store.get_inferred_requests()
        raw_document = build_openapi_document(requests, request.site)
        validate_openapi(raw_document)

        overlay = load_overlay()
        public_document = apply_overlay(raw_document, overlay)
        validate_openapi(public_document)

        for finding in lint_openapi_document(public_document):
            print(f"openapi lint: {finding}")

        return (
            DocumentOutput(filename=RAW_FILENAME, kind="source", extension="yaml", content=_as_yaml(raw_document)),
            DocumentOutput(filename="redaction.overlay", kind="rule-catalog", extension="yaml", content=_as_yaml(overlay)),
            DocumentOutput(filename=PUBLIC_FILENAME, kind="source", extension="yaml", content=_as_yaml(public_document)),
        )
