# `generators/usability_act.py`

## module

`usability-rules.json` + `usability.earl.jsonld` + `usability.sarif.json`
+ `usability.md`, per docs/adr/0011 - ACT Rules Format 1.1 rule catalog,
EARL 1.0/JSON-LD findings, a mechanical SARIF projection, and a view
rendered from both.

Serialization only: every finding still comes from
`generators/usability.py`'s deterministic detection rules, unchanged -
the same `build_X`/adapter split every other generator here uses.

## RuleDefinition

One hand-authored rule (ADR-0011 point 4) - `CONTEXT.md`'s Rule catalog:
fixed for a rule-set version, not derived from any crawl. Five entries,
one per distinct `Finding.rule` `usability.py`'s detection functions can
produce; `tests/test_usability_act.py`'s own consistency test catches a
sixth detection rule appearing with no matching catalog entry.

## build_rule_catalog

`usability-rules.json` - hand-authored, fixed for this rule-set version,
never derived from a crawl. `RULE-<heuristic-slug>-<NN>` ids (ADR-0011
point 2), sequential per Nielsen heuristic - two rules share "consistency
and standards" today, so they're `-01`/`-02`.

## build_earl_document

`usability.earl.jsonld` - the real per-run source document, one
`Assertion` per finding `usability.py::build_findings` produced.
`mode` is always `earl:automatic`: every rule here is a deterministic
pattern/heuristic detection, never an LLM-flagged judgment call or a
HITL-confirmed one (ADR-0011 point 3's other two modes, neither of
which exists yet). `derived_from`/`axtree_ref` stay reserved - no
stable per-interaction/HAR/screenshot id scheme, and no dedicated
finding-to-AXTree-node correlation pass (the same gap `catalog.json`'s
`x-region.axtree_ref` left reserved, ticket #101).

## build_sarif_document

`usability.sarif.json` - a pure mechanical projection of
`usability.earl.jsonld`'s findings (ADR-0011 point 4): `ruleId`/`level`/
`message`/`location` read straight off each `Assertion`, no remapping -
the point of ADR-0011 point 1's own "severity defaults at the rule
level... the export needs no remapping" design. Lists every catalog rule
in `tool.driver.rules` regardless of whether it fired this run, which is
what lets a CI consumer diff "rules available" from "rules that found
something."

## _render_usability_view

`usability.md` - mechanically rendered from `usability-rules.json` and
`usability.earl.jsonld`, never hand-authored in parallel. The empty case
says the audit was *narrow*, not that the application is usable - six
deterministic rules finding nothing means six rules found nothing, and a
document reading "no findings" with no qualifier would be taken as a
clean bill of health. Also names what is not covered and why: loading
indicators during a request, and whether a failed submit told the user,
both need the DOM observed *during* an interaction, which the crawl does
not do.

## UsabilityDocument

Four outputs: `usability-rules.json` (`kind="rule-catalog"`),
`usability.earl.jsonld` (`kind="source"`), `usability.sarif.json`
(`kind="projection"` - `CONTEXT.md`'s reshaping-pragma's-own-data-into-
an-external-standard sense, the same category `architecture.calm.json`/
`architecture.cyclonedx.json` already established for the graph), and
`usability.md` (`kind="view"`). Registered as `"usability"`, the same
name the retired single-output `UsabilityDocument` used before this
split.
