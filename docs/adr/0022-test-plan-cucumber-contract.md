# `test-plan` cites by gherkin's own tags, normalizes status to EARL's outcome

**Status**: accepted

The ticket frames its first two open points as a choice between two Cucumber JSON conventions to
reuse. Research shows neither is a reliable target: Cucumber JSON has no single governing spec, its
`id` field isn't emitted by every Gherkin runner (`behave` has none at all), and its `status` enum
varies by implementation — 4 values in `behave`, 5 in `cucumber-js`, 6 in `cucumber-jvm`. Both
questions resolve the same way: don't couple to a target that isn't stable across the tooling a
staging rebuild might actually use.

Decided, resolving the ticket's three open points:

**1. Citation via `gherkin`'s Own Tags, Not Cucumber JSON's `id`.** Confirmed against the actual
formatter source of multiple Gherkin runners: a scenario's tags (`@REQ-<hash>`, `@confidence:<level>`,
`@EP-<hash>`, `@MOD-<x>`, `@SCR-<hash>` — ADR-0013) survive verbatim into Cucumber JSON's `tags`
array regardless of which runner produced it — cucumber-js, cucumber-jvm, and `behave` all preserve
them unfiltered. Cucumber JSON's own `id` (a `feature-name;scenario-name` slug) isn't universal
across runners and carries no semantic content a tag doesn't already provide better. `test-plan`
entries cite scenarios by tag, not by a runner-dependent id.

**2. Status: EARL's `outcome`, Normalized at Ingestion.** Cucumber JSON's native status field has no
single enum to reuse — it differs by implementation. `test-plan.json` uses EARL's `outcome`
(`passed`/`failed`/`cantTell`/`inapplicable`/`untested`, the convention `usability`/`accessibility`
already established, ADR-0011/0012), with whatever a specific staging run's test-runner actually
emits normalized into that vocabulary at ingestion — the same pattern `accessibility` used for
axe-core's `impact`→SARIF `level` (ADR-0012). `test-plan.json` isn't tied to any one runner's
dialect; the normalization step is where that dialect gets absorbed.

**3. Meaningful Pre-Staging State.** Because citation is via `gherkin`'s own stable tags rather than
a runner-generated id, `test-plan.json` has a real state before any staging environment exists:
every scenario `gherkin` emits gets an entry with `outcome: "untested"` — EARL's actual value for
"testing process not yet performed" — until something executes it. Not an empty or absent document
waiting for infrastructure; a fully-populated one waiting for status updates.

Depends on `gherkin`'s tag vocabulary (ADR-0013).

Wayfinder ticket: [test-plan: close the loop from gherkin scenarios to staging runs](https://github.com/ezequielrickert/pragma/issues/86),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
