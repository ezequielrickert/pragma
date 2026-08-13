# `src/generators/json_schema.py`

## module

The only place that knows both of this project's two type languages.

The **shape language** is internal: `network_filter._json_shape` produces
it (every value replaced by its type name, so a body can be described
without ever persisting a real one) and `request_family._merge_shape`
unions it across samples, marking a key some samples lacked with a
trailing `?`.

**JSON Schema** is what OpenAPI needs. Keeping the translation here means
the capture side never hears about OpenAPI and the document side never
hears about how shapes are captured - either can change without the other
moving.

## _scalar_schemas

`"null"` maps to `{"nullable": True}` with no `type`, because OpenAPI 3.0
has no null type of its own - it spells "this may be null" as a keyword on
an otherwise-typed schema. A value observed only ever as null gives no
other type to attach it to, which is exactly what the bare `nullable`
says.

## schema_from_shape

Returns `{}` rather than raising or inventing when there is nothing to
describe, and there are two distinct ways to get there:

- No shape at all (`""`). A classic form submit sends
  `application/x-www-form-urlencoded`, which `_shape_of_json_text` cannot
  parse and correctly refuses to guess at. An empty schema means
  "anything", which is the truth.
- An unrecognised type name. The shape language is produced upstream and
  could gain a name before this module hears about it; degrading that one
  property to "anything" beats failing the whole document over it.

`required` is emitted only when non-empty: OpenAPI permits `required: []`
but it reads as a deliberate statement that nothing is required, rather
than as the absence of information.
