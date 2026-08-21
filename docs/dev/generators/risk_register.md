# `generators/risk_register.py`

## module

`risk-register.json` - structurally-observable risk flags on
`architecture.cyclonedx.json`'s third-party services, docs/adr/0024.

**Why one rule, and why this one.** Pragma's crawl captures no HTTP
response headers, no client-side library/version strings, and no
third-party status/auth signal anywhere in its current graph schema -
confirmed by reading `database/ladybug/network.py`'s own write path, not
assumed. "Known information-disclosure header names" (`_DISCLOSURE_HEADER_NAMES`)
is the one rule buildable without either a maintained EOL-version
database (which "outdated version strings" would need, and which this
pipeline has no deterministic, non-network way to judge) or new crawler
instrumentation (out of scope for a document-generation ticket, matching
every other reserved-instrumentation gap this map has already deferred).

**Why this isn't empty-forever the way `asyncapi` is.** `asyncapi.json`
raises because no coherent document shape exists without real channel
data at all. `risk-register.json`'s container (an array of
schema-real entries) is fully meaningful today even at zero rows - the
same "reserved, not fabricated" posture `evidence-log`/`redaction-log`
already established for a legitimately-empty run.

## detect_structural_risks

Pure function over a CycloneDX document - real, deterministic, and
testable via a fixture today even though `DISCLOSED_HEADERS_PROPERTY` is
always empty in an actual crawl. Once a future header-capture pass
populates that property on `architecture.cyclonedx.json`, this starts
reporting for real with zero changes to this module.

## _disclosed_headers

Splits `DISCLOSED_HEADERS_PROPERTY`'s comma-separated value - the
reserved format `architecture_cyclonedx.py`'s own `_external_service`
already declares.

## build_risk_register

Recomputes `architecture.cyclonedx.json`'s own document directly from
the graph (`build_cyclonedx_document`) rather than reading a file
`architecture` may not have written this run - the same "call the real
build function" discipline every cross-generator call in this map
already follows.

## _render_risk_register_view

Mechanically rendered from `risk-register.json`'s own entries - never
hand-authored in parallel with it.

## RiskRegisterDocument

Source (`risk-register.json`, schema-validated) + view
(`risk-register.md`) split. The empty-register view note is unconditional
prose, not a bare "nothing found" line - a reader should learn *why* an
empty register doesn't mean the site's third-party integrations carry no
risk at all (live CVE lookup is reserved, not built).
