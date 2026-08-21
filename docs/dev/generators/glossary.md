# `generators/glossary.py`

## module

`glossary.jsonld` - SKOS/JSON-LD domain vocabulary, `TERM-<hash>` ids,
docs/adr/0020.

**Why field names, not free text.** `data-model.json`'s fields are
already structured, low-noise vocabulary; component/page copy is not,
and mining it for "recurring business terms" without inventing false
positives is a real, separate problem this ticket doesn't take on. A v2
could add it as a second term source.

**Why recurrence (2+ entities), not every field.** A field declared on
exactly one entity is real, but nothing observed it *recurring* - the
"is this a meaningful, reusable business concept" test ADR-0020 point 3
sets. Promoting a one-off field to a glossary term would claim more than
the crawl actually showed.

## _normalize_label

Lowercase + strip only - no accent-folding, no stemming. `TERM-<hash>`
needs *a* deterministic normalization to collapse `"Email"`/`"email"`
into one concept, not the most sophisticated one; a field name is
already close to canonical (it is the application's own submitted key,
`_field_name`'s first-choice source), so this stays simple.

## term_id

`TERM-<hash>` (ADR-0020 point 1) - hashes `_normalize_label`'s output,
never the raw label, so casing differences never mint two concepts for
the same term.

## _field_occurrences

`{field_name: [entity_name, ...]}`, both keys and the entity list sorted
- the recurrence count `build_glossary_document` filters on, and the
raw material `cross_references` cites directly.

## build_glossary_document

The one filter that matters: `len(entities) >= 2`. Everything else -
`broader`/`narrower`/`related` reserved, `derived_from`/`axtree_ref`
reserved - is the same "state the gap, don't invent" discipline every
other document in this map already applies to evidence it has no
correlation pass for yet.

## _render_glossary_view

Mechanically rendered from `glossary.jsonld`. The empty case is
unconditional prose, not a bare "no terms" line - a reader should learn
*why* an empty glossary doesn't mean "this site has no domain
vocabulary," the same "the dangerous output is the empty one" discipline
`accessibility.md`'s own scope note follows.

## GlossaryDocument

Source/view split, matching every other multi-file document in this map.
`extension = "jsonld"` for the source output - the same convention
`usability.earl.jsonld`/`accessibility.earl.jsonld` already established
for a JSON-LD document that isn't plain `.json`.
