# `generators/gherkin_tags.py`

## module

The store-dependent half of docs/adr/0013's tag vocabulary, split out of
`generators/gherkin.py` (ticket #107) once the module crossed the
file-size-audit SPLIT threshold: `gherkin.py` reshapes a `Trace`'s own
fields (no store, no graph metrics), this module correlates a `Trace` to
`requirements.py`'s extraction rules and to the graph's module/screen ids.
Unlike the `usability`/`usability_act` split, there's no circular-import
risk being dodged here - just a genuine store-dependent/pure boundary.

## _endpoint_tag_id

`EP-<hash>` (ADR-0013 point 1) is a hash of `target` -
`f"{method} {endpoint}"`, `requirements.py`'s own composite string - which
already equals the graph's real `Endpoint.id`
(`database/ladybug/ids.py::endpoint_id`, `"METHOD host/path_pattern"`)
exactly. No separate `host`/`path_pattern` needed: `InferredRequest.endpoint`
is already `host` + `path_pattern` concatenated.

## trace_screens

The start page, plus every page a navigating step actually landed on, in
visiting order - the set `@SCR-<hash>` and `@MOD-<x>` both resolve
against.

## TraceCorrelations

Every real correlation one trace's steps have to `requirements.py`'s own
extraction rules - `requirement_ids` and `endpoint_ids`, computed together
by `correlate_trace` in one pass rather than two.

## correlate_trace

One store read (`get_inferred_requests()`), one pass, both `@REQ-<hash>`
and `@EP-<hash>` computed together - not two independent walks over the
same data. Recomputes exactly what `requirements.py`'s own
`_event_driven_requirements`/`_ubiquitous_requirements`/
`_unwanted_behavior_requirements` would derive, restricted to the
`InferredRequest`s this trace's own steps genuinely `triggered_by`/
`loaded_by`, so `requirement_id` always lands on the identical
`REQ-<hash>` `requirements.json` itself would emit for that same
observation - never a second, independently-derived id.

`unwanted_behavior` only fires for an endpoint this trace already
`touched` - a failure on an endpoint this trace never called isn't this
trace's own requirement to demonstrate.

## screen_module_ids

`{SCR-<hash>: MOD-<slug|hash>}`, reading `module_id` (not
`requirements.py`'s human-readable `module_label`) off
`core.graph_metrics.compute_graph_metrics` - the literal tag id
ADR-0013 point 2 locked.

## module_tags

Every module a trace's visited screens resolve to, deduplicated - most
traces stay within one module, but a trace that navigates across a module
boundary carries every one it touched.

## scenario_tags

The exact tag tokens, as a tuple - `@REQ-<hash>` + `@confidence:observed`
always come first and are never omitted (ADR-0013 point 3) - a scenario
reaching this function already has at least one requirement id, since
`build_scenarios` filters out anything that doesn't before rendering.
`confidence` is a literal `"observed"`, not computed per-tag:
`event_driven`/`ubiquitous`/`unwanted_behavior` are the only EARS
patterns a trace step can ever correlate to, and `requirements.py` never
emits any of the three at any other confidence. This tuple is verbatim
what Cucumber JSON's own `tags` array carries regardless of runner
(ADR-0022 point 1) - `test_plan.py` cites scenarios by it directly.

## tag_line

`scenario_tags`, joined into one indented Gherkin tag line - the only
form `render_scenario`/`render_scenario_outline` need.
