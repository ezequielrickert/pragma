# generators/flows.py

## module

Flow derivation - one `SemanticFlow` per `Trace`, per 'Define Flow semantics
and derivation algorithm' (issue #189, part of the same map as
`screens.py`). Pure and deterministic, no model call: the derivation
research (issue #186) found `name`/`goal` fully templatable from data
already on the `Trace`, so unlike `Screen` this tier needs no separate
narration module.

Written for every trace, including one whose terminal step neither
navigated nor fired a request - `flows_arazzo.py::_is_observable` excludes
those because Arazzo has nothing executable to say about them; `Flow` is
describing what happened, where a dead-end path is itself useful to see.

## _terminal_step

The trace's last step, or `None` for an empty trace - the one place that
decision is made, shared by every tier below that reads off "how did this
journey end".

## _humanized

`"createOrder"` -> `"Create order"` - `operation_id_for`'s own camelCase,
split into words and re-capitalized as a phrase rather than an identifier.
No new vocabulary: a formatting transform over the exact string
`openapi.yaml` already carries.

## _terminal_request

The `InferredRequest` behind the trace's own terminal step, if its firing
component correlates to one - the same `(page_url, path) in triggered_by`
correlation `flows_arazzo.py::_step_operations` uses, narrowed to one step
since a Flow's name cites where the journey ended, not every call it made
along the way. Sorted by `(method, endpoint)` when more than one candidate
correlates, so the choice is reproducible rather than dependent on read
order.

## _GOAL_VERB_TAXONOMY

Closed goal-verb taxonomy (issue #196): a keyword-to-phrase table that
overrides tier-1's raw CRUD-verb phrase whenever the terminal request's
`endpoint` case-insensitively contains one of a phrase's keywords,
regardless of HTTP method - `logout`/`signout` -> "Log out",
`checkout`/`pay` -> "Purchase", `signup`/`register` -> "Sign up",
`login`/`signin` -> "Log in", `search` -> "Search", `delete`/`remove` ->
"Delete", first match wins in that order. Local to this module, never
shared with `generators/openapi.py`'s `operation_id_for`/`_summary` -
changing those would change already-emitted `openapi.yaml` content, a
separate decision.

## _goal_verb_override

The taxonomy phrase for an endpoint string, or `None` if no keyword
matches - a thin lookup over `_GOAL_VERB_TAXONOMY`.

## _name_and_goal

The `(name, goal)` cascade: terminal-endpoint CRUD phrase (subject to the
`_GOAL_VERB_TAXONOMY` override), else terminal `route_shape`, else the
generic step-count fallback - first tier with something to say wins, per
issue #189's resolution. The taxonomy override applies only within tier 1,
unconditionally, per issue #196's resolution; tier 2's `route_shape`
fallback is untouched.

`Trace.end_page` always resolves to something (it falls back to
`start_page` itself when nothing navigated), so the tier gate asks the
terminal step directly (`terminal.navigated`) rather than trust that
property's own truthiness - this mirrors the ticket's own definition of
"non-observable" (the terminal step neither navigated nor fired a
request), which the three tiers here match one-for-one.

## _outcome

The terminal step's own fired-request outcome, bucketed via
`generators/user_flows.py::request_outcome` - no separate taxonomy.

## build_flows

One `SemanticFlow` per trace the crawl walked, in `build_traces`'s own
order (longest first, then `visit_id`). `derived_from` carries each step's
real `step_seq` (`TraceStep.step_seq`, added for this ticket) rather than a
recomputed position - a visit's stamped sequence can have gaps, so only
the real value round-trips to the matching `Interaction` node
`database/ladybug/flow.py::record_flows` needs.
