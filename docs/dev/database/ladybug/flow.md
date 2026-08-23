# database/ladybug/flow.py

## module

`Flow` write and read path for `LadybugGraphStore` - the semantic tier's
third writer, following `screen.py::record_screens`'s pattern
(full-rebuild-per-run, `DERIVED_FROM`-provenanced, no-provenance-no-write).

**Deletes are scoped by source label, same reasoning as `screen.py`.**
`DERIVED_FROM` is one rel table shared by every semantic-tier writer - a
blanket delete here would erase whichever other writer ran first on this
same run. `record_flows` deletes only `Flow`-sourced `DERIVED_FROM` edges.
`STEP_OF` needs no such scoping: the schema declares it `FROM Interaction
TO Flow` only, so it has exactly one writer and a blanket delete is
unambiguous.

**A `Flow` has no natural-key property to re-`MATCH` after creation** -
unlike `Screen` (`page_url`, unique via `Page`) or `Entity`/`Field`
(`name`), two dead-end traces of equal length from the same start page
would produce an identical `name`/`goal`/`step_count`/`outcome`, so
matching a freshly created Flow back by its own properties could attach
one trace's `STEP_OF`/`DERIVED_FROM` edges to the wrong node. Each Flow's
node creation and all of its edges are written in one Cypher statement
instead (`CREATE ... WITH fl UNWIND ... MATCH ... CREATE ...`), keeping the
new node bound for the whole statement rather than re-finding it.

## _ladybugflowmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`, the same
contract every other mixin in this package has.

## record_flows

Replaces this site's `Flow` set with `flows` - a full rebuild, like
`record_screens`: a Flow has no stable identity across a rebuild that adds
or removes traces, so patching in place isn't sound.

Raises `ValueError` if any flow has no `derived_from` - mirrors
`record_entities`/`record_screens`'s own enforcement: this tier is only
worth having if every node in it can be traced back to what it was
observed from.

Each Flow's `STEP_OF`/`DERIVED_FROM` edges are written by `UNWIND`ing its
`derived_from` step sequences and `MATCH`ing the `Interaction` node at
`{visit_id, step_seq}` for each one - the same `(visit_id, step_seq)` key
`database/ladybug/network.py::record_component_network` already matches
Interactions by.

## get_flows

Every `Flow` with its steps, ordered by `visit_id` - the `visit_id`
recovered from its own `STEP_OF`-linked `Interaction` nodes, since `Flow`
stores no `visit_id` property of its own (see `SemanticFlow`'s own
docstring for why). Grouping by `visit_id` alone is unambiguous:
`build_flows` writes exactly one Flow per `Trace`/`visit_id`, so every row
sharing a `visit_id` belongs to the same Flow and carries the same
`name`/`goal`/`step_count`/`outcome`.

Rebuilt into the same `SemanticFlow` shape `build_flows` produces, same
round-trip property `get_screens` maintains for `SemanticScreen`.
