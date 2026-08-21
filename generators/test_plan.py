"""`test-plan.json` - closes the loop from `gherkin` scenarios to a real
staging run, docs/adr/0022.

**Citation via `gherkin`'s own tags, not Cucumber JSON's `id`** (ADR-0022
point 1). Cucumber JSON has no single governing spec, and its `id` field
(a `feature-name;scenario-name` slug) isn't emitted by every runner
(`behave` has none at all). A scenario's own tags (`@REQ-<hash>`,
`@confidence:observed`, ...) survive verbatim into every runner's `tags`
array regardless of dialect - confirmed against cucumber-js, cucumber-jvm,
and `behave`'s own formatter source - so entries cite scenarios by the
exact tag tuple `generators.gherkin.build_scenarios` already produces,
never a runner-dependent id.

**Status: EARL's `outcome`, normalized at ingestion** (ADR-0022 point 2).
Cucumber JSON's own status field has no single enum: 4 values in `behave`,
5 in `cucumber-js`, 6 in `cucumber-jvm`. `normalize_outcome` absorbs every
dialect into EARL's fixed vocabulary (`passed`/`failed`/`cantTell`/
`inapplicable`/`untested`) - the same normalize-at-ingestion pattern
`accessibility` already used for axe-core's `impact` (ADR-0012).

**A meaningful pre-staging state, not an empty document** (ADR-0022 point
3). Because citation is via `gherkin`'s own stable tags rather than a
runner-generated id, every scenario `gherkin` writes gets a `test-plan`
entry with `outcome: "untested"` the moment it exists - a fully-populated
document waiting for status updates, never an empty one waiting for a
staging environment.

**Ingestion has no live caller yet.** `ingest_cucumber_json` is real and
unit-tested against a sample Cucumber JSON document, but nothing wires an
actual staging run's output into `request.settings["test_results"]` -
the same "reserved via settings until a real caller exists" state
`change-log.json`'s own `previous_snapshot` is already in. Absent, every
entry stays `"untested"`, never invented as anything else.

Details: docs/dev/generators/test_plan.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema
from .gherkin import GherkinScenario, build_scenarios

_SCHEMA_PATH = "schemas/test-plan.schema.json"

# The union of every status a `behave`/cucumber-js/cucumber-jvm legacy
# JSON formatter can emit, mapped to EARL's outcome vocabulary
# (ADR-0022 point 2). `skipped` -> `inapplicable`: a runner skip is a
# deliberate decision (a tag filter, an earlier step's own failure) that
# the scenario did not run this pass - closer to "not applicable this
# run" than to `untested`, which this document reserves for "never
# staged at all." `undefined`/`pending`/`ambiguous` -> `cantTell`: each
# means the runner itself could not determine pass or failure (no step
# definition matched, one not yet implemented, or more than one
# matched) - EARL's own "unclear whether the subject passed or failed."
_RUNNER_STATUS_TO_OUTCOME: Dict[str, str] = {
    "passed": "passed",
    "failed": "failed",
    "skipped": "inapplicable",
    "undefined": "cantTell",
    "pending": "cantTell",
    "ambiguous": "cantTell",
    "untested": "untested",
}

# Worst-first, for aggregating several step or scenario outcomes into
# one: a scenario is only as good as its worst step, and a Scenario
# Outline (whose every Examples row inherits the Outline's own tags,
# so every row's Cucumber JSON element shares one tag tuple) is only as
# good as its worst row.
_OUTCOME_SEVERITY: Dict[str, int] = {"failed": 0, "cantTell": 1, "inapplicable": 2, "untested": 3, "passed": 4}


def normalize_outcome(runner_status: str) -> str:
    """One runner's own status string, normalized to EARL's outcome
    vocabulary. An unrecognized string (a new runner, a typo) becomes
    `cantTell` rather than being silently miscounted as passed or failed.
    Details: docs/dev/generators/test_plan.md#normalize_outcome
    """
    return _RUNNER_STATUS_TO_OUTCOME.get(runner_status, "cantTell")


def _worst_outcome(outcomes: Sequence[str]) -> str:
    return min(outcomes, key=lambda outcome: _OUTCOME_SEVERITY[outcome])


def _scenario_outcome(element: Dict[str, Any]) -> str:
    statuses = [normalize_outcome(step.get("result", {}).get("status", "")) for step in element.get("steps", [])]
    return _worst_outcome(statuses) if statuses else "untested"


def _tag_name(tag: Any) -> str:
    """One tag from a Cucumber JSON `tags` array, however this runner
    shaped it - cucumber-js/cucumber-jvm's own legacy JSON formatter
    emits `{"name": "@x", "line": N}`; `behave`'s strips the `@` at
    parse time and its formatter emits a bare `"x"` string, no wrapping
    object. Normalized to the one `@`-prefixed string `scenario_tags`
    itself produces, so citation is symmetric regardless of dialect.
    Details: docs/dev/generators/test_plan.md#_tag_name
    """
    name = tag["name"] if isinstance(tag, dict) else tag
    return name if name.startswith("@") else f"@{name}"


def ingest_cucumber_json(cucumber_document: List[Dict[str, Any]]) -> Dict[Tuple[str, ...], str]:
    """`{tags: outcome}` for every scenario a real runner's Cucumber JSON
    output reports - `tags` exactly as `scenario_tags` produces them (the
    same verbatim `@`-prefixed strings, ADR-0022 point 1), so the result
    looks up directly against `build_scenarios`'s own output.
    Details: docs/dev/generators/test_plan.md#ingest_cucumber_json
    """
    outcomes_by_tags: Dict[Tuple[str, ...], List[str]] = {}
    for feature in cucumber_document:
        for element in feature.get("elements", []):
            tags = tuple(_tag_name(tag) for tag in element.get("tags", []))
            outcomes_by_tags.setdefault(tags, []).append(_scenario_outcome(element))
    return {tags: _worst_outcome(outcomes) for tags, outcomes in outcomes_by_tags.items()}


def _plan_entry(scenario: GherkinScenario, outcomes_by_tags: Dict[Tuple[str, ...], str]) -> Dict[str, Any]:
    return {
        "scenario": scenario.title,
        "tags": list(scenario.tags),
        "outcome": outcomes_by_tags.get(scenario.tags, "untested"),
    }


def build_test_plan(request: DocumentRequest) -> List[Dict[str, Any]]:
    """One entry per `gherkin`-generated scenario, `outcome` defaulting to
    `"untested"` until `request.settings["test_results"]` supplies a real
    Cucumber JSON document to ingest.
    Details: docs/dev/generators/test_plan.md#build_test_plan
    """
    scenarios, _ = build_scenarios(request)
    test_results = request.settings.get("test_results")
    outcomes_by_tags = ingest_cucumber_json(test_results) if test_results is not None else {}
    return [_plan_entry(scenario, outcomes_by_tags) for scenario in scenarios]


def _render_test_plan_view(entries: List[Dict[str, Any]]) -> str:
    """`test-plan.md` - mechanically rendered from `test-plan.json`, never
    hand-authored in parallel with it.
    Details: docs/dev/generators/test_plan.md#_render_test_plan_view
    """
    lines = ["# Test Plan", ""]
    if not entries:
        lines.append(
            "No gherkin scenario exists to plan against. `test-plan.json` mirrors gherkin.feature "
            "one-to-one - a crawl with no traceable interaction traces produces neither."
        )
        return "\n".join(lines) + "\n"

    counts: Dict[str, int] = {}
    for entry in entries:
        counts[entry["outcome"]] = counts.get(entry["outcome"], 0) + 1
    lines.append(f"{len(entries)} scenario(s): " + ", ".join(f"{count} {outcome}" for outcome, count in sorted(counts.items())))
    lines += ["", "| Scenario | Outcome | Tags |", "|---|---|---|"]
    lines += [
        f"| {entry['scenario']} | {entry['outcome']} | {' '.join(entry['tags'])} |"
        for entry in entries
    ]
    lines.append("")
    return "\n".join(lines)


@DOCUMENT_REGISTRY.register("test-plan")
class TestPlanDocument(DocumentGenerator):
    """`test-plan.json` (source, schema-validated) and `test-plan.md`
    (view) - docs/adr/0022.
    Details: docs/dev/generators/test_plan.md#testplandocument
    """

    name = "test-plan"
    title = "Test Plan"
    purpose = "Every gherkin scenario, cited by its own tags, with a staging outcome - untested until a real run reports otherwise."

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        entries = build_test_plan(request)
        validate_against_schema(entries, _SCHEMA_PATH)
        view = _render_test_plan_view(entries)
        content = json.dumps(entries, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        return (
            DocumentOutput(filename="test-plan", kind="source", extension="json", content=content),
            DocumentOutput(filename="test-plan", kind="view", extension="md", content=view),
        )
