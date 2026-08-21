# `generators/test_plan.py`

## module

`test-plan.json` - closes the loop from `gherkin` scenarios to a real
staging run, docs/adr/0022. Cites scenarios by `gherkin`'s own tags
(never Cucumber JSON's runner-dependent `id`), normalizes whatever a
specific runner's Cucumber JSON dialect emits to EARL's `outcome`
vocabulary, and defaults every scenario to `"untested"` - a real,
populated document from the moment `gherkin.feature` exists, not an
empty one waiting for a staging environment.

**Ingestion has no live caller yet.** `ingest_cucumber_json` is real and
tested against sample output, but nothing wires an actual run's Cucumber
JSON into `request.settings["test_results"]` - the same reserved-until-
wired state `change-log.json`'s own `previous_snapshot` is already in.

## normalize_outcome

The union of every status `behave`/cucumber-js/cucumber-jvm's legacy
JSON formatters can emit, mapped to EARL's fixed vocabulary. `skipped`
reads as `inapplicable` (a deliberate runner decision that the scenario
didn't run this pass), `undefined`/`pending`/`ambiguous` all read as
`cantTell` (the runner itself couldn't determine pass or failure). An
unrecognized string becomes `cantTell` rather than being silently
miscounted as passed or failed.

## _tag_name

`behave`'s own tag model strips the `@` at parse time and its JSON
formatter emits a bare string, no wrapping object; cucumber-js/
cucumber-jvm's legacy formatter emits `{"name": "@x", "line": N}`.
Normalized to one `@`-prefixed string either way, rather than picking a
side - a real, documented shape difference across runners, not a guess.

## ingest_cucumber_json

`{tags: outcome}`, keyed by the exact tag tuple `scenario_tags` produces
- looks up directly against `build_scenarios`'s own output. A `Scenario
Outline`'s every `Examples` row inherits the Outline's own tags, so its
Cucumber JSON elements all share one tag tuple; aggregated to their
worst shared outcome, since an Outline is only as good as its worst row
the same way a scenario is only as good as its worst step.

## build_test_plan

One entry per `generators.gherkin.build_scenarios` scenario - the exact
list `gherkin.feature` itself renders from, so the two documents can
never silently drift apart.

## _render_test_plan_view

Mechanically rendered from `test-plan.json`'s own entries: an outcome
tally, then one table row per scenario. The empty case names *why*
there's nothing to plan against - `gherkin.feature` produced no
scenario either - rather than reading as a blank plan.

## TestPlanDocument

Source (`test-plan.json`, schema-validated) + view (`test-plan.md`)
split, matching every other multi-file document in this map.
