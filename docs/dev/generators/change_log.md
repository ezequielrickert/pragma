# `generators/change_log.py`

## module

`change-log.json` - a cross-run diff over every entity kind that already
carries a Short hash ID, docs/adr/0019.

**Why `interaction:`/`har:` are excluded.** `evidence-log` (ADR-0017)
already established their Kùzu `SERIAL` ids aren't stable across
re-crawls - diffing them would compare noise, not signal, not a real
change in the application.

## EntityChange

## EntityDiff

One kind's own three-way split (ADR-0019 point 2) - `newly_discovered`/
`no_longer_observed` carry just the id; `changed` carries the id plus
`before`/`after` (the raw field dicts, for a caller that wants the full
detail) and `changed_fields` (what the schema/view actually surface).

## diff_entities

**The one algorithm every entity kind uses.** Deliberately has no
special-casing for "did the identity change" - it can't, because an
entity's identity change is invisible to this function by construction:
identity-defining fields are baked into the Short hash id itself
(`SCR-<hash>` from the route, `REQ-<hash>` from `ears_pattern` + `trigger`
+ `target`, ...), so a changed identity means a *different* dict key, not
the same key with a different value. `diff_entities` only ever sees "this
key is new" or "this key is gone" or "this key's value changed" - the
`no_longer_observed`+`newly_discovered` pair ADR-0019 point 2 requires
falls out of the id-as-key structure on its own.

`changed_fields` also catches a field that was present before and is
gone now (or vice versa), not just a changed value - `set(before) |
set(after)`, not `set(after)` alone.

## _screen_id / _endpoint_id

`build_export_graph`'s own `Pantalla`/`Endpoint` nodes are keyed by their
*raw* identity (a page url, `"{method} {endpoint}"`) rather than
`SCR-<hash>`/`EP-<hash>` - those two forms are always minted by whichever
document needs them, never carried by `export.json` itself. The exact
same formula `generators/graph_export.py::_requisito_nodes` already uses
internally to resolve a `Pantalla`'s `SCR-<hash>` for its own
`implementa` edges - not a new convention invented here.

## _snapshots_from_export_graph

One `build_export_graph` call backs four of the six kinds -
`Requisito`/`Modulo` nodes already carry their real `REQ-<hash>`/
`MOD-<slug|hash>` id as `node["id"]`, used as-is; `Pantalla`/`Endpoint`
get `SCR-`/`EP-` minted from their raw id. Calling `build_export_graph`
once here, rather than calling `build_requirements_document` a second
time directly, avoids exactly the redundant recomputation that would
otherwise happen (`build_export_graph` already calls
`build_requirements_document` once internally, for its own `Requisito`
population).

## _current_snapshots

`channels`/`messages` stay empty on purpose - `AsyncAPIDocument.generate`
has no real detection instrumentation to read from yet (ADR-0018,
ticket #111). Present in the shape anyway, the same forward-looking
reason `asyncapi.json`'s own `CH-`/`MSG-` id scheme was built before real
data existed to mint one from.

## build_change_log_document

**`previous_snapshot is None` is a genuinely different case from
`previous_snapshot == {kind: {}}`.** The first means no caller has wired
a previous run in at all - `run_id_from` stays `null` and every kind's
diff is an honest empty one, not "everything currently observed is
newly discovered," which would misrepresent a single-run site as having
just experienced a huge burst of new entities. The second means a real
previous run genuinely had nothing of that kind - a real diff proceeds
normally, and everything in the current snapshot legitimately is newly
discovered.

No caller wires `request.settings["previous_snapshot"]` yet - reading
`runs.json` (`utils/io.py::record_run_manifest`), resolving which of
that run's `document_paths` entries is the *source* file for a given
kind, and parsing it back into a snapshot is real work a future ticket
does. This ticket's own "Done when" is the diff algorithm itself, proven
against synthetic fixtures - see `tests/test_change_log.py`.

## _render_change_log_view

Mechanically rendered from `change-log.json`, grouped by kind - a kind
with nothing to report (all three lists empty) contributes no section at
all, so a mostly-quiet run's view stays short instead of listing six
empty headings.

## ChangeLogDocument

Source/view split (ADR-0019 point 3: a genuine per-run-pair source
document, the opposite of `CONTEXT.md`'s Rule catalog definition - the
diffing algorithm is static code, but its output is crawl-derived).
