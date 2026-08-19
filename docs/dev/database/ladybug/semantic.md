# database/ladybug/semantic.py

## module

The semantic tier's write and read path - the tier `schema.py` declared and
nothing wrote until this module.

**The tier split is the whole point, and provenance is what makes it real.**
The observation tier records what the crawl saw. The inferred tier records
deterministic clustering over that. This one records what the application
*means*, which is a different kind of claim living in the same database, and
the only thing keeping the two distinguishable is that every node here can be
traced back to the observations supporting it.

So `record_entities` **raises** on a node with no `derived_from` rather than
writing an unsupported assertion. `schema.py` had already stated the rule in a
comment; a rule that lives only in a comment is one a future writer breaks by
accident, and the write is the single place it cannot be forgotten.

`Screen`, `Flow` and `Rule` still have no writer. `Rule` stays frozen for the
reason `research/plan-generacion-de-documentos.md` Fase 7 froze it - its value
was almost entirely the human-in-the-loop review that is out of scope - and
the other two have no consumer asking for them.

## _ladybugsemanticmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`, the same contract
every other mixin in this package has.

## record_entities

A full rebuild, like `record_component_families`. The derivation is a pure
function of the component ledger, so a second run over a changed graph must
not leave the previous run's entities sitting beside the new ones.

**Edges are deleted before nodes.** Ladybug refuses to delete a node that
still has relationships attached, so `DERIVED_FROM`, `HAS_FIELD` and `EDITS`
go first. That failure is loud rather than silent, but it only appears on the
*second* run, which is a bad place to discover it.

Validation runs over every entity and field before any write happens.
Rejecting halfway through would leave the tier half-rebuilt.

## _link_provenance

One `DERIVED_FROM` edge per supporting component, carrying `method`,
`confidence`, `run_id` and `generator`, so a reader can tell which pass
concluded what without joining anything.

`MERGE` on the `Component`, never `MATCH`. A `MATCH` that matches nothing
drops the entire pattern silently - the trap `containment.py` documents - so a
component missing from the graph would cost the provenance edge with no error
at all, which is exactly the failure this module exists to prevent.

## _write_field

**Why `EDITS` and `DERIVED_FROM` are both written**, even though they point at
the same components today: they answer different questions. `EDITS` is "this
field is edited through that control", a structural fact a rebuild needs.
`DERIVED_FROM` is "this field appears in the document because of that
control", a provenance fact a reader needs in order to judge it.

They coincide because the current derivation is one-to-one. A later derivation
that reads two controls to conclude one field would separate them, and
collapsing them now would make that change look like a data migration.

## get_entities

Rebuilt into the same `SemanticEntity` shape `build_entities` produces, so a
round-trip through the store compares equal - the property
`get_component_families` already maintains for `ComponentFamily`, and what
`tests/test_data_model.py::test_entities_round_trip_through_the_store` pins.

## _provenance_by_node

One query per label rather than per node. An entity with twelve fields would
otherwise cost thirteen round trips through the single writer thread for data
that is one `MATCH` away.

Page urls come from `split_component_id` rather than a second hop through
`HAS_COMPONENT`: the page is already encoded in the component id, and that
function is the one place that knows how it is encoded.
