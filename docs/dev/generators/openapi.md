# `src/generators/openapi.py`

## module

D4 in `research/plan-generacion-de-documentos.md`: an OpenAPI 3.0 contract
built from the traffic a crawl actually saw.

**No model call anywhere.** Every field is a rearrangement of what
`request_family.build_inferred_requests` already grouped. That is what
makes the output usable as a contract - something a client generator or a
mock server consumes - rather than as a summary someone has to re-check.

**What it cannot contain, by construction.** Security schemes, headers and
examples are absent because the crawler records the *shape* of every
request and response and never the values
(`network_filter._json_shape`) - a deliberate privacy decision, not a
missing feature. There is no captured Authorization header to describe.
The document states this in its own `info.description` instead of looking
complete, which matters: a reader who assumes an endpoint needs no auth
because the spec says nothing would be wrong in a way that costs them a
day.

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

## _operation_id

Singular for everything except a listing: `POST /orders` creates one
order, so `createOrders` would be wrong about what the operation does.
`listOrders` keeps the plural because a listing genuinely returns many.

This is the name that ends up in generated client code, so the number is
worth getting right even though nothing validates it.

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

The registry adapter. `extension = "yaml"` is what keeps
`pipeline._with_banner` from prepending the coverage banner - a YAML file
with a Markdown blockquote glued to the front no longer parses. The
coverage caveat still reaches the reader, through the `info.description`
preamble.
