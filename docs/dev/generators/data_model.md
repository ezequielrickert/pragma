# generators/data_model.py

## module

D14/`data-model.json`, and the semantic tier's first inhabitant, per
docs/adr/0008.

**Entities are still forms-only, and that is a schema constraint rather
than a modelling preference.** `DERIVED_FROM` declares `FROM Entity TO
Component` and `FROM Field TO Component`, with no pair reaching a
`Request` - naming a *new* entity purely from an API body shape (no form
`id`/context) is exactly the kind of guess this tier can't show its work
for. Since ticket #103, an *existing* field's `observed_in.api_endpoints`
(ADR-0008 point 2) is correlated against API traffic anyway - a
document-generation-time computation, not a graph write, so it needs no
`DERIVED_FROM` edge and no migration to the write path. This fixes the
format audit's own complaint (ADR-0008's intro): a field present in API
traffic but unexposed in the HTML form was undercounted before.

Pure and deterministic. Naming a form's noun - "this is a Checkout" - is
exactly the kind of guess this tier is supposed to be able to show its work
for, and it cannot, so it is not attempted.

## _data_types

Declared input types mapped onto `SemanticField.data_type`'s vocabulary.
Anything unlisted stays `"string"`: the job is to report what the markup
declares, not to normalise it into something tidier than it is.

## _field_types

A button is part of a form and is not a field of the entity the form collects.
Matched by `component_type` prefix, which
`component_classifier.classify_component_type` already computed at crawl time -
this module does not re-derive what a control is.

## _field_name

`name` first, because that is what the application itself uses when it
submits; then label, then placeholder, which are what it shows a person. A
field with none of the three is dropped by `build_entities` rather than
emitted under an invented name.

## _validation

Only what the markup declares. Inferring a rule from the values a crawl
happened to submit ("always four digits") would be a guess dressed as a
constraint, and this tier is the one place in the project where that
distinction carries weight.

## _entity_name

The form's `id` where it has one, else the page's last path segment - the only
other captured thing that carries intent.

Deliberately never a noun inferred from the field names. A form with `email`
and `password` might be a login, a signup or an invite; the data does not say
which, and a document that guesses cannot show its work for the guess.

## group_form_components

`{(page_url, form_selector): [component, ...]}` - the grouping
`build_entities` turns into `SemanticEntity`/`SemanticField` objects and
`build_data_model_document` reads directly, since the JSON assembly
needs the raw `form_selector` a `SemanticEntity`'s own `description`
only carries as prose. Factored out of `build_entities` (ticket #103)
so both callers share one grouping pass instead of two independently
maintained copies.

## build_entities

Grouped by `(page_url, form_selector)`, not by selector alone. `form` is
`el.closest('form')`'s selector as recorded by discovery, so two forms on one
page stay two entities and the same form seen on two pages stays two. Merging
those would assert an identity nothing in the data supports.

Inputs outside any form are skipped: a lone search box is not a thing the
application collects, and promoting every stray input to an entity produces a
document of noise.

The declared type is reported, never corrected. A field named for an email but
declared as plain text reads as a string here; D7's
`missing_semantic_input_type` is the document that reports the gap, and
silently fixing it in this one would hide that finding.

## _pii_signals

Field-name substrings mapped onto a W3C DPV category/type and a
sensitivity default (ADR-0008 point 1) - a small, stated heuristic, not
an exhaustive privacy audit. False negatives (a PII field this table
misses) are the safe failure mode; the signal list stays narrow and
specific rather than broad, to avoid a false positive flagging an
unrelated field as personal data.

## _privacy_annotation

`None` for a field this heuristic has no opinion about - absent from the
document entirely, never a false `is_pii: false` presented as a real
finding. Matches by substring against a normalized (letters-only,
lowercased) field name, so `billing_address`/`user_email_confirm` still
match `address`/`email`.

## _api_citations

Every endpoint whose observed request or response body carries a key
matching a field's name (case-insensitive) - the fix for the format
audit's own complaint (ADR-0008's intro): fields present in API traffic
but unexposed in HTML forms were undercounted before. No graph schema
change needed - this is computed at document-generation time, reading
`InferredRequest.body_shape`/`response_shape` (already JSON-encoded
structural shapes, `generators/json_schema.py`'s own input format) and
matching on their keys.

## _confidence

A stated, deliberately simple v1 heuristic (matching `openapi.yaml`'s
own `x-inference.confidence`, docs/adr/0004): 0.7 for a form-declared
field alone, +0.2 when API traffic corroborates it, +0.1 when it recurs
across more than one screen.

## _gaps

One gap per unfinished page (docs/adr/0008 point 3) - `entity` names the
page itself, since no form-derived name exists for a page the crawl
never reached. `unvisited_endpoint` reuses `coverage.json`'s own
page-level gap data (`coverage.unfinished_urls`): pragma has no way to
detect a genuinely unvisited *API* endpoint it never observed a link or
reference to, unlike an unfinished page, which the crawl frontier
already tracks.

## build_data_model_document

Assembles the full `data-model.json` payload: one entity per form
(`group_form_components`), each field annotated with multi-source
provenance and, where a naming heuristic matched, a DPV privacy object -
plus the coverage gaps this crawl left.

## _mermaid_identifier

A Mermaid-safe identifier - alphanumeric and underscore only, since
`erDiagram` entity/attribute names don't tolerate the punctuation a form
`id` or a field `name` can carry.

## _mermaid_er_diagram

A native Markdown Mermaid `erDiagram` block (docs/adr/0008 point 4) -
one entity block per form, no relationship lines: pragma's forms are
independent, unrelated by anything the crawl observed, and drawing a
connection between them would be a guess this document doesn't make
anywhere else.

## _render_data_model_view

`data-model.md` - mechanically rendered from `data-model.json`'s own
fields (type/nullable/confidence/privacy/observed_in), never the
`SemanticField` dataclass's own extra attributes (declared validation,
observed values): the view renders only what the source document
actually carries, per the Source/View split every other document here
follows.

## datamodeldocument

Two outputs since ticket #103: `data-model.json` (source, schema-
validated) and `data-model.md` (view). The empty state names both
causes - no form reached, or forms whose inputs carry nothing to
identify them - because from here they look identical.
