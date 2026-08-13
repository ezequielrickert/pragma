# `src/generators/traces.py`

## module

Ordered traces: one page visit's interactions in the order they happened,
each with the requests it actually fired.

This is what `VisitStep` was stamped for, and two documents read it - the
Gherkin specification, whose scenarios *are* traces, and the flow
document, which uses per-step request attribution to stop labelling a
successful branch with a failed one's status.

## TraceStep

## Trace

`end_page` is the last step that navigated, not the last step. A trace
often ends with an interaction that changed something in place; the screen
the user is left on is the last one they were moved to.

## requests_for

Selects the requests one specific interaction fired, rather than the pool
its control accumulated.

Falls back to the whole pool when nothing on the control is stamped -
data written before stamping existed. Deliberately the pool and not an
empty list: an unattributable request is still evidence, and returning
nothing would silently drop it. Callers that need to know which case they
are in check for stamps themselves (`user_flows._requests_for_move` does).

## build_traces

Interactions with no `visit_id` are **skipped entirely**, not appended at
the end. They carry no position, so placing them anywhere in a sequence
whose whole value is its order would be inventing that order. A crawl
predating the stamping therefore produces no scenarios at all, which the
Gherkin document says out loud rather than rendering an empty file.
