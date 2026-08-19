# `architecture` splits into a CALM structure projection and a CycloneDX third-party projection

**Status**: accepted

The format audit's section 3.2 leaves `architecture` genuinely contested: two competing standards
for module/container structure, two competing standards for the third-party-integration inventory,
and whether `arc42` survives the "no duplicate views" rule. This ADR locks both formats, splits
`architecture` into two source documents plus one view, and defines how each source document
relates to the graph.

Decided, resolving the ticket's three open points (plus the follow-on decisions the format choices
opened up):

**1. Module/Container Structure.** Adopt **FINOS CALM 1.2** over Structurizr DSL. Structurizr scores
better for LLM-generation and is the de-facto standard, but its own DSL would be the first source
document in this pipeline that isn't JSON-Schema-validable — every other locked document (`coverage`,
`export`, `tree`, `openapi`, `tokens`, `catalog`) converged on JSON/YAML+JSON-Schema specifically so
the dashboard can validate and render everything through one code path.

**2. Third-Party Integration Inventory.** Adopt **CycloneDX 1.6** over SPDX 3.0, using its
`externalServices` construct — purpose-built for an *observed service dependency* (what pragma
detects via traffic-domain analysis), where SPDX's object model centers on installed-package
provenance.

**3. `arc42` Survives as a View.** `architecture.md` stays arc42-shaped, generated mechanically from
the two source documents below — never hand-authored in parallel. Its section structure (context,
building blocks, deployment view, risks) is a standard reading convention for architecture docs
specifically, the same category as ACT Rules Format or MADR in `CONTEXT.md`'s glossary, not a
duplicate view.

**4. Both Source Documents Are Projections, Not Independent Detection.** `architecture.calm.json`
and `architecture.cyclonedx.json` are generated *from* the live graph (`export`'s vocabulary, ADR-0002)
rather than running their own detection pass — the same call `export` itself made. Concretely:
CALM's nodes/relationships are reshaped from `Pantalla`/`Componente`/`Endpoint`/`Modulo` and the
`contiene`/`navega_a`/`dispara`/`consume` edges; CycloneDX's `externalServices` reads directly off
`Endpoint` nodes where `first_party = false` (already present in `database/ladybug/schema.py`, no
new graph entity required). A second, independently-detected module/component structure is exactly
the divergence risk this ticket's own scope-cut (deferring module derivation to `#72`) was already
guarding against.

**5. Two Source Documents, Not One.** `architecture.calm.json` and `architecture.cyclonedx.json`
ship as separate files. CALM and CycloneDX are independently-versioned external standards, each with
its own root schema (`$schema` / `bomFormat` requirements) — one JSON root can't validate against
both at once. `architecture.md` renders from both, the same cross-document-citation pattern
`catalog.md` already uses via `x-tokens` into `tokens.json` (ADR-0006).

**6. CALM Node-Type and Edge Mapping.** CALM's node-kind enum is open (`node-type` accepts any
string; the 9 recognized values — `actor`, `ecosystem`, `system`, `service`, `database`, `network`,
`ldap`, `webclient`, `data-asset` — are infra-shaped and don't fit a scraped SPA's screen/component/
endpoint/module vocabulary, and CALM has no `container`/`component` kind at all: containment is a
*relationship*, not a node-type). Pragma's own vocabulary ships as the literal `node-type` string
(`"screen"`, `"component"`, `"endpoint"`, `"module"`) rather than being force-fit into CALM's
sanctioned kinds — semantic fidelity over generic-visualizer polish, the same tradeoff `tree`'s
`x-`-namespaced extensions and `catalog`'s `x-region` already made. Edges map directly: `contiene` →
CALM `composed-of` (`container`/`nodes`); `navega_a`/`dispara`/`consume` → CALM `connects`
(`source`/`destination`, each satisfied by a bare `{"node": "<unique-id>"}` — CALM's `node-interface`
requires only `node`, so no per-node `interfaces` array needs to be synthesized).

**7. Provenance Extensions, Per Format's Own Mechanism.** CALM's `node`/`relationship` objects allow
`additionalProperties: true` plus a free-form `metadata` field, so pragma's evidence and confidence
data nest directly: `metadata: { pragma: { evidence: [...], confidence: {...} } }`, mirroring
`tokens.json`'s existing `$extensions.pragma.*` pattern (ADR-0005). CycloneDX's `service` object
locks `additionalProperties: false`; its sanctioned extension point is a flat `properties: [{name,
value}]` array. `pragma` is registered as a top-level namespace in the upstream
`cyclonedx-property-taxonomy` repository, with flat colon-delimited keys — `pragma:evidence:source`,
`pragma:evidence:harRequestId`, `pragma:evidence:observationCount` — rather than a single JSON-blob
value, matching the taxonomy's own flat, single-valued property convention.

Wayfinder ticket: [architecture: choose structure and third-party-inventory formats](https://github.com/ezequielrickert/pragma/issues/71),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
