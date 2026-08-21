# `generators/browser_support_matrix.py`

## module

`browser-support-matrix.json` - locked ready for observed legacy-browser
evidence no instrumentation captures yet, docs/adr/0028. The same
"entirely absent today, on purpose" posture `asyncapi.py`/
`i18n_inventory.py` already established: `getComputedStyle()`
(`discover_components.js`) always normalizes a vendor-prefixed property
to its standard name, so it structurally cannot see one; no capture
reads raw script source at all.

## TechnicalEvidence

Synthetic today - what a future polyfill/vendor-prefix/UA-sniffing
detection pass would supply for one observation.

## vendor_prefix_query

Real, well-known vendor-prefix-to-browser-family associations (the CSS
Working Group's own registry), not a guess.

## ua_sniff_query

Real, well-known user-agent substrings (`MSIE`/`Trident` for Internet
Explorer, `Presto` for old Opera) - a substring this table doesn't
recognize returns `None` rather than a fabricated guess.

## build_browser_support_matrix

`business_reason` always `None` - nothing here is inferable from the
site, only a human review pass (reusing `prd`'s `hitl_status` pattern,
ADR-0009) fills it in.

## BrowserSupportMatrixDocument

Registered so `manifest.json` can enumerate it as `status: "off"` - not
so it can actually run. There is no store method to call
`build_browser_support_matrix` with.
