# `flows` splits UI/API statecharts, folds `sequences` in as a rendered section

**Status**: accepted

The format audit's sections 3.9 and 3.12 lock XState JSON for UI-level statecharts and Arazzo for
API-level call sequences — two distinct graphs today's single `flows` document wrongly conflates —
and call for `sequences` to become a derived view rather than its own hand-authored document. Both
XState and Arazzo turn out to have native mechanisms for everything the ticket worried about needing
a custom extension for: Arazzo's `successCriteria` already supports compound body assertions beyond
a bare status code, and its `Step` object already cross-references OpenAPI `operationId`s natively.
This ADR locks the cross-reference convention, the `successCriteria` policy, guard documentation,
and `sequences`' fate.

Decided, resolving the ticket's three open points (plus pinning Arazzo's exact version):

**1. Cross-Reference Convention.** XState states cite their screen via `meta.screen`: `"SCR-<hash>"`
(ADR-0003) — bare, not nested under a `pragma` key the way CALM's `metadata.pragma` is (ADR-0010).
CALM's nesting guards against a third-party CALM tool also writing into the same object; this
machine JSON is pragma's own generated output exclusively, so there's no collision to guard against.
Arazzo steps cite their operation via the spec's own native `operationId` field (Arazzo v1.1.0 §5.8.5)
— no extension needed, since Arazzo was built specifically to reference operations in a linked
OpenAPI `sourceDescriptions` document.

**2. Guard Documentation.** XState v5's guard object has exactly two fields, `type` and `params` — no
native `description`. Guards are documented via `params.description` (plain-language condition) and
`params.derived_from` (evidence pointers — `interaction:<id>`/`har:<id>`/`screenshot:<id>`, the
convention `prd`/`usability`/`accessibility` already locked), since `params` is the only confirmed
extension point on a guard; nothing about guessing at an unconfirmed transition-level field.

**3. Arazzo Version and `successCriteria` Policy.** Pin **Arazzo 1.1.0** specifically — its
`Criterion` type enum (`simple`/`regex`/`jsonpath`/`xpath`) and JSONPath version identifier
(`rfc9535`) both changed from 1.0.0, and the ticket's own "1.0/1.1" framing was ambiguous. Every step
carries a baseline `simple` status-code criterion. A second `jsonpath`-typed criterion (e.g.
`context: $response.body`, `condition: $.estado != 'error'`) is appended only when pragma's crawl
evidence actually showed the same status code returned with a body field whose value correlated with
success/failure — never asserted unconditionally on every operation regardless of whether that
pattern was observed, matching the evidence-gated posture `openapi`'s `x-inference` already set
(ADR-0004).

**4. `sequences` Folds Into `flows`, Not Its Own Document.** `sequences` is removed from
`DOCUMENT_REGISTRY` entirely rather than surviving as a mechanically-regenerated file of its own. A
Mermaid `sequenceDiagram` block, generated from the XState machine or the Arazzo workflow, becomes
one section of `flows.md`'s view. A separate file carrying zero information `flows.md` doesn't
already have would be exactly the kept-in-sync-for-no-reason surface this whole map exists to
eliminate.

**5. Document Split.** `flows.xstate.json` (UI statecharts, source document) + `flows.arazzo.json`
(API call sequences, source document — two files, matching `architecture`'s CALM/CycloneDX
precedent of ADR-0010, since both are independently-versioned external standards with their own root
schema) + `flows.md` (view, rendered from both, including the folded-in sequence diagrams per point
4).

Wayfinder ticket: [flows: lock contract (XState + Arazzo), fold in sequences](https://github.com/ezequielrickert/pragma/issues/78),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
