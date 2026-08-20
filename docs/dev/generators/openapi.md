# `generators/openapi.py`

## module

D4 in `research/plan-generacion-de-documentos.md`: an OpenAPI 3.1 contract
built from the traffic a crawl actually saw (docs/adr/0004, ticket #99 -
upgraded from 3.0.3 for 1:1 compatibility with the JSON Schema draft
2020-12 version `coverage.json` already locked).

**No model call anywhere.** Every field is a rearrangement of what
`request_family.build_inferred_requests` already grouped. That is what
makes the output usable as a contract - something a client generator or a
mock server consumes - rather than as a summary someone has to re-check.

**What it cannot contain, by construction.** Field constraints (enum,
pattern, minimum) are absent - they need many values per field to infer
and would be guesses from one observation. Security schemes are named
from request header names only (`_security_scheme`), never from a
credential - this says which scheme an endpoint uses, never what the
token was. The document states both limits in its own
`info.description` instead of looking complete.

## _crud_verbs

GET is deliberately absent from the table. It means "list" when the call
carries query parameters and "get" when it doesn't - the one method whose
verb depends on more than itself.

## path_template

`normalized_endpoint` collapses every opaque segment to the same `{id}`,
which is correct as a grouping key and **invalid** as an OpenAPI path:
`/orders/{id}/items/{id}` declares one parameter name twice, and the spec
requires them unique.

Each parameter is renamed after the segment before it, singularised -
`/orders/{orderId}/items/{itemId}`. That fixes validity and reads better
than a numbered fallback. The numeric suffix exists only for the case
where two preceding segments produce the same name anyway.

## _verb_and_subject

Singular for everything except a listing: `POST /orders` creates one
order, so `createOrders` would be wrong about what the operation does.
`listOrders` keeps the plural because a listing genuinely returns many.

This is the name that ends up in generated client code, so the number is
worth getting right even though nothing validates it. `_operation_id` and
`_summary` both read from here, so `createOrder` and "Create order" can
never disagree about what an operation does.

`summary` is a phrase ("List orders"), not a restatement of the
operationId. An earlier version repeated the id plus the raw endpoint,
which also printed `{id}` one line under a path key reading `{orderId}` -
the same parameter under two names.

## _schemaregistry

Deduplicates identical schemas into `components/schemas` and references
them with `$ref`, so a shape shared by several operations is written once.

Schemas with no properties are returned **inline** instead: a named
component for `{}` is a lookup that explains nothing, and it would fill
the components section with entries for every endpoint whose body was
never JSON.

Keyed by the schema's own serialised form rather than by name, so two
endpoints that happen to share a shape share a component even when their
resource names differ - which is the case worth deduplicating.

## _responses

One entry per status code actually observed, and a single `default` entry
saying so when none were.

The alternative - assuming `200` - is how an inferred spec becomes
misleading: a reader has no way to tell a status that was seen from one
that was assumed, and the `422` an endpoint really returns would be
missing while a `200` it never returns is present.

## per-path-servers

A crawl spanning several hosts (an app and its auth service, say) cannot
be described by one top-level `servers` list: that claims every path
exists on every server.

OpenAPI allows `servers` on an individual Path Item, so each path names
the host it was observed on. Emitted only when there is more than one
host, since the single-host case is exactly what the top-level list is
for.

## build_openapi_document

Takes already-inferred requests rather than a `GraphStore`, so the whole
assembly is testable without a store and the generator class stays a
three-line adapter. Same split as every other generator here.

## OpenAPIDocument

The registry adapter - since ticket #99, three outputs per docs/adr/0004:
`openapi.raw` (`kind="source"`), `redaction.overlay` (`kind="rule-catalog"`,
a copy of whatever `config/redaction.overlay.yaml` held this run - the
same "fixed for a rule-set version" shape `CONTEXT.md`'s Rule catalog
entry names, provenance rather than a re-derivation), and `openapi`
(`kind="source"`, the public file - the overlay applied to the raw
document). All three validated against the real OpenAPI 3.1 schema
(`openapi_spec_validator.validate`) before being written; a document
that isn't valid OpenAPI at all is a harder failure than anything
`generators/openapi_lint.py` checks, so it isn't caught locally - it
propagates the same way any other generator's exception does.

`extension = "yaml"` on every output is what keeps
`pipeline._with_banner` from prepending the coverage banner - a YAML
file with a Markdown blockquote glued to the front no longer parses. The
coverage caveat still reaches the reader, through the `info.description`
preamble.

## _confidence_ceiling

Five independent observations of the same operation is treated as full
confidence - a deliberately simple, stated v1 heuristic (docs/adr/0004's
`x-inference.confidence`), not a statistical model. One named constant so
the number is stated once, not repeated at each of the three fields it
scales.

## _confidence

`0.0` when there is no data to be confident in at all (no body ever
captured, say) - genuinely unknown, not "confidently absent." Otherwise
scales toward `1.0` as `observation_count` approaches
`_CONFIDENCE_CEILING_OBSERVATIONS`.

## _inference

The `x-inference` extension. `methods_inferred` is always `[]` in v1:
this crawler infers a path's *shape* and a body's *structure* from
observed samples, but never an HTTP method nobody actually called -
"PUT is probably also supported" would be exactly the invention this
document's own preamble disclaims.

`path_params` confidence is `1.0` when the path carries no parameter at
all - a verified structural fact (`path_template` found no opaque
segment), not a guess, so it needs no observation count behind it.
`request_schema`/`response_schema` are `0.0` under the same "no data"
condition, since the absence of a captured body is not verified the same
way - the endpoint might take one, the crawl just never triggered a call
that carried it.

`x-observed-roles` (docs/adr/0004's other named extension) is omitted
from every operation in v1, deliberately, not defaulted to an empty
`{allowed: [], denied: []}`: the crawl never authenticates as more than
one role (`coverage.json`'s own `roles: ["anon"]`), so there is no real
allowed/denied observation to report yet. Reserved rather than invented -
activates once role-differentiated crawling exists (see map #94's Out of
scope).

## _load_overlay

`config/redaction.overlay.yaml`, or the empty default when the file is
missing - a maintainer who hasn't added a rule yet is a valid v1 state
(capture-time redaction, `spiders/content/redaction.py`, already ran),
not an error this generator should refuse to run without.

## _security_scheme

One observed scheme as an OpenAPI `securitySchemes` entry, from what
`network_filter._auth_scheme` reported - `bearer`, `basic`, `cookie`, or
`header:x-api-key`.

**An unrecognised scheme becomes an `http` scheme under its own name rather than
being dropped.** An unfamiliar `Authorization` scheme is still authentication,
and omitting it would tell a reader the endpoint is open - the one error this
document could make that actively misleads.

## media-types

`responses:` uses the media type the server actually answered with, rather than
assuming `application/json`.

An endpoint that returns XML or a redirect is common enough that assuming JSON
would make the contract wrong for exactly the endpoints a reader is least likely
to check by hand.
