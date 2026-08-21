# `generators/user_flows.py`

## module

D6: the state machine the crawl walked.

Needs no new capture. Every transition is a `NAVIGATED_TO` edge already
written during the crawl, and the endpoint and status on it come from
network requests already sitting on the triggering component.

**The error branches are the reason to read it.** A diagram of the happy
path restates the navigation menu. One showing the checkout POST answering
422 and landing back on the form describes how the application actually
behaves - and those are the paths a rebuild has to keep working.

**docs/adr/0014, ticket #108.** This `FlowGraph` now also backs
`flows.xstate.json` (an XState v5 machine) - the API-level half
(`flows.arazzo.json`, one workflow per observed trace) needs a different,
per-visit data source and lives in `generators/flows_arazzo.py`.
`FlowsDocument` (was `UserFlowsDocument`) wires both source documents plus
the view together. `sequences` folded into `flows.md`'s own final section
instead of surviving as its own file (point 4).

## FlowTransition

## FlowGraph

`entry_states` and `dead_ends` fall out of the same edge set for free.
`dead_ends` is not only a drawing aid: "a screen with no way out" is a
usability finding (Nielsen's user control and freedom), and the 5a
document reads it from here rather than recomputing it.

The document is careful about how it phrases them, though: a dead end can
equally be a screen whose exits the crawl never reached, and the coverage
document is what tells the two apart.

## _request_outcome

A failure outranks a success on the same control. A screen answering 201
for most inputs and 422 for some is interesting *because* of the 422, and
summarising it by the happy path hides exactly the branch worth
documenting.

## mixed

The honest limit of the first version of this document, found by rendering
it rather than by reasoning about it. **Now resolved for any graph crawled
with interaction stamping** (see `_requests_for_move`); what follows is
why it existed and why the marker is still reachable.

Requests are stored **per interaction** - `record_component_network`
appends one JSON batch per interaction - but `get_component_ledger`
flattens every batch into one list when reading back. So a control clicked
twice, once landing on `/receipt` and once bouncing back to `/cart`, has
both requests pooled together with nothing saying which belongs to which.

The first version picked the worst request for every transition of that
control, which labelled the **successful** branch with the failed one's
422. That is a plain false statement about the application, and precisely
what this document exists to avoid.

Now: a control leading to one screen keeps its exact outcome; a control
leading to several whose requests disagree gets `mixed`, the endpoint
still reported and the status withheld. Where every request agrees there
is no ambiguity to flag, so the outcome stands.

Fixing it properly needed per-interaction attribution to survive the read,
which is the `visit_id`/`step_seq` stamping Fase 6 added. It now does, so
a current crawl resolves each branch exactly. The marker remains for
graphs written before that, where the ambiguity is real and must not be
papered over by machinery that cannot actually see the answer.

## build_flow_graph

`get_edges` is written with `CREATE`, so a page visited twice writes the
same edge twice. That repetition is real history and belongs in the store;
it is noise in a state machine, so transitions are deduplicated here,
keyed by `(from, to, trigger, action)`.

An edge whose component is missing from the ledger still produces a
transition, labelled by its path. The navigation genuinely happened -
dropping it because its label is poorer would hide a real move.

## render_state_diagram

Mermaid state identifiers have to be plain tokens and real routes are not
(`/orders/{id}` alone would break the parser), so states get `s0`, `s1`
ids with the route as a separate label line.

Trigger text is stripped of `:` before being used as an edge label: a
colon is what separates a Mermaid state id from its label, so one inside a
button's text (`Total: 500`) would silently corrupt the line rather than
fail loudly.

## _render_flow_view

The state diagram, transitions table, error branches, and dead-ends
sections `UserFlowsDocument` used to render directly, pulled out into
their own function once `FlowsDocument.generate` needed to append the
folded-in sequence-diagram section (ADR-0014 point 4) after them.
States up front how requests are attributed and when that attribution
fails - see `_requests_for_move`. A reader taking a per-move status at
face value should know whether it was resolved or pooled.

## _screen_id

`SCR-<hash>` (ADR-0003), computed straight from the route-shaped state
string - the same convention `requirements.py`/`gherkin_tags.py` already
use for a page url.

## _guard

XState v5's guard object has exactly two fields, `type` and `params` - no
native `description`. `params.description`/`params.derived_from`
(ADR-0014 point 2) are the plain-language condition and the reserved
evidence pointers; `type` carries the same `ok`/`error`/`unknown` value
`FlowTransition.outcome` already has, so a reader (or a real XState guard
function keyed by `type`) doesn't need a second vocabulary.

## _state_events

An event fires exactly one target when the crawl only ever observed one
destination for that trigger; it becomes an array of guarded branches
only when the *same* trigger really did lead to more than one
destination - a fact `FlowGraph`'s existing `(from, to, trigger, action)`
transition keying already preserves, so this needed no change to
`build_flow_graph` itself, only a new grouping pass over its output.

## build_xstate_document

The one entry point: a `FlowGraph` and a site name in, an XState v5
machine config out. Mints its own `s0`/`s1`... state ids via the same
`_state_ids` Mermaid rendering already uses, so both outputs agree on
which short id names which real screen.

## FlowsDocument

States up front how requests are attributed and when that attribution
fails - see `_requests_for_move`. A reader taking a per-move status at
face value should know whether it was resolved or pooled.

Both source documents are schema-validated before the view is rendered,
so a structural mistake in either fails the whole `generate()` call
rather than shipping a `flows.md` that describes JSON `flows.xstate.json`/
`flows.arazzo.json` don't actually contain.

## _requests_for_move

The fix for what `mixed` was introduced to declare.

Interactions now carry the position they happened at (`VisitStep`), and so
do the requests they fired, so a control clicked twice has each click's
response separable from the other's. A move is matched to its own
interactions by comparing `route_shape(resulting_url)` to the destination
state - the interaction stores the literal URL, the edge stores the shape.

Falls back to the control's pooled requests, flagged inexact, when nothing
is stamped. That flag is what keeps `mixed` alive for graphs written
before the stamping existed: a document reading an old graph must not
silently gain precision it does not have.
