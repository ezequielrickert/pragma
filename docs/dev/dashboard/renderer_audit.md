# `dashboard/renderer_audit.py`

## module

Which registered document gets a dedicated Phase B renderer, and which
falls back to the generic template - ADR-0016 point 3's own audit,
ticket #123's first half.

**Why openapi is the one exception.** Redoc (`redoc.standalone.js`) is
ADR-0016 point 2's own named reference case - real, single-script,
actively maintained. Every other external standard this map adopted
was checked for a matching single-script embed and found wanting: CALM
and CycloneDX have viewer tooling but nothing embeddable without a
Node build; JSON Schema/DTCG/Custom Elements Manifest/SARIF/ACT
Rules/EARL/XState/Arazzo/Gherkin all have the same gap. Every
pragma-native document was never going to have a third-party renderer
to look up in the first place - there's no external standard behind
it.

**Why three names are absent, not marked "generic."**
`asyncapi`/`i18n-inventory`/`browser-support-matrix` all `raise` in
`generate()` (ADR-0018/0027/0028) - no file ever exists for either
renderer to apply to, a different fact than "gets the generic
template."

## renderer_for

Defaults to `"generic"` for a name the table hasn't been extended for -
the same "unlisted sorts as the ordinary case" posture
`master_document.py`'s own resolution-order table already takes,
applied here so a future document needs no change to this function,
only a new table entry when it actually clears the reuse bar.
