# generators/data_model.py

## module

D14, and the semantic tier's first inhabitant.

**Forms only, and that is a schema constraint rather than a modelling
preference.** `DERIVED_FROM` declares `FROM Entity TO Component` and `FROM
Field TO Component`, with no pair reaching a `Request`. An entity deduced from
an API body shape therefore could not record where it came from, and the rule
this tier exists to uphold is that nothing enters without provenance.

Adding that pair is one line of DDL and a migration problem: `CREATE REL TABLE
IF NOT EXISTS` does not alter an existing table, so every `.lbdb` already on
disk would silently keep the old shape. Until there is a migration story, the
API side of the model stays in D4, which describes it honestly as shapes.

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

## datamodeldocument

Registered as `data-model`. The empty state names both causes - no form
reached, or forms whose inputs carry nothing to identify them - because from
here they look identical.

The header states the two things a reader would otherwise have to infer: that
names are the form's own id rather than a guessed noun, and that types and
validation are what the markup declares.
