# Chat grounding draws from every real citation across generated documents, not `export.json` alone

**Status**: accepted

[Interactive dashboard](https://github.com/ezequielrickert/pragma/issues/146)'s own charting
recommended `export.json` as the chat's primary grounding source. Checked against the actual
vocabulary before locking that: `export.json` only ever populates `Pantalla`/`Componente`/
`Endpoint`/`Token`/`Modulo`/`Entidad`/`Requisito` (`generators/graph_export.py`'s own module
docstring) - `Escenario`/`Hallazgo`/`Flujo`/`Estado` stay reserved by design, so `gherkin`,
`usability`/`accessibility`, and `flows` have **no node in the graph at all**. `risk-register.json`
doesn't go through `export.json` either - it cites `architecture.cyclonedx.json`'s own
`externalServices[].name` directly (`generators/risk_register.py`). `export.json` alone would
leave roughly half this pipeline's documents with nothing to ground a chat answer in.

Checked what those documents actually cite instead, rather than assuming none of them do:

- `content-inventory.json` cites `custom-elements.json`'s own variant
  (`component_ref`: `"<catalog component name>#variant-<N>"`) and `SCR-`-prefixed screen ids
  (`schemas/content-inventory.schema.json`) - both real, structured, resolvable identifiers.
- `change-log.json` diffs by the same short-hash ids `export.json`'s own nodes already use
  (`SCR-`/`REQ-`/`EP-`/`MOD-`, `generators/change_log.py`) - a change-log entry's id resolves
  directly against `export.json`.
- `decisions.adr/`'s own records cite the `REQ-<hash>` they explain - resolves to a real
  `Requisito` node.
- `usability.earl.jsonld`/`accessibility.earl.jsonld`'s own `subject.@id` (`generators/usability.py`/
  `accessibility.py`'s `Finding.where`) is **not** uniformly a structured id - checked the real
  assignments: a per-component finding's `where` is `f"{page_url} — {path}"` (an em-dash, not
  `component_id()`'s own `|` separator - reconcilable, but not identical), while a family-level or
  endpoint-level finding's `where` is a human-readable description (`"{component_type} (N
  instances)"`, `"{method} {endpoint}"`) with no structured id underneath it at all. Real citations
  exist here, but not a single uniform format to resolve mechanically for every finding.
- `gherkin`'s `.feature` scenarios and free prose inside `prd.md`/`catalog.md` cite nothing
  structured - there is genuinely no real dependency fact to ground a claim about these in today.

Decided:

**1. Grounding is tiered by what's actually real, not a single source.** Given an edit target,
the grounding pipeline tries, in order: (a) `export.json`'s own graph, when the edited document
has real node coverage there (`tokens`, `catalog`/`custom-elements`, `data-model`, `prd`,
`architecture`'s CALM/`Modulo` side); (b) another already-generated document's own real,
structured citation field, when the edited document has one (`risk-register`'s `service_ref` into
`architecture.cyclonedx.json`, `content-inventory`'s `component_ref`/`screens`, `change-log`'s
short-hash ids, `decisions.adr`'s `REQ-` reference); (c) nothing, honestly, when neither applies
(`gherkin`, `flows`, free prose, or a `usability`/`accessibility` finding whose own `where` field
carries no structured id).

**2. A finding's `where` field gets a best-effort structured-id extraction, not a guaranteed one.**
Attempt to parse a per-component `where` (`"page_url — path"`) back into `component_id()`'s own
`"page_url|path"` form when it matches that shape; when it doesn't (a family/endpoint-level
finding), fall through to tier (c) for that specific finding rather than fabricating a component
reference that isn't really there.

**3. Tier (c) is a real, expected outcome, not a bug to route around.** The chat says "no real
dependency data exists for this edit" plainly when every tier comes up empty - never invents a
consequence to fill the gap, matching this pipeline's own discipline everywhere else (reserved
fields, honest empty arrays, `_NOT_YET_PRODUCED`-style notes).

**Consequence**: the grounding pipeline needs one dispatcher per document name (which tier applies,
and how to extract the resolvable id from that document's own real field), not one universal
`export.json`-only lookup. Building that dispatcher, and the local-model prompt that consumes its
output, is separate implementation work this ADR doesn't itself specify.

**Side finding, fixed where cheap**: `dashboard/document_context.py`'s own `content-inventory`
example (ticket #145) showed a fabricated `"component": "example.com/checkout|p.legal"` field that
doesn't match the real schema at all - corrected to the real `component_ref`/`screens` shape found
while researching this ADR.
