# `src/generators/user_flows.py`

## module

D6: the state machine the crawl walked.

Needs no new capture. Every transition is a `NAVIGATED_TO` edge already
written during the crawl, and the endpoint and status on it come from
network requests already sitting on the triggering component.

**The error branches are the reason to read it.** A diagram of the happy
path restates the navigation menu. One showing the checkout POST answering
422 and landing back on the form describes how the application actually
behaves - and those are the paths a rebuild has to keep working.

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

## UserFlowsDocument

States up front how requests are attributed and when that attribution
fails - see `_requests_for_move`. A reader taking a per-move status at
face value should know whether it was resolved or pooled.

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
