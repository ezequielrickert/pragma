# `generators/i18n_inventory.py`

## module

`i18n-inventory.json` - locked ready for locale variants no
instrumentation observes yet, docs/adr/0027. The same "entirely absent
today, on purpose" posture `asyncapi.py` already established for WS/SSE
traffic (ADR-0018): zero `hreflang`/URL-locale-segment detection exists
in this crawl, `generate()` always raises, and `run_document_pipeline`'s
existing skip-and-log degradation is what turns that into
`manifest.json`'s honest `status: "off"`.

**A layer, not a third copy mechanism** (point 2). `message_key` cites
`content-inventory`'s own `component_ref` or `glossary`'s `TERM-<hash>`
- never a second, independently-captured copy of the observed string
itself.

## LocaleVariant

Synthetic today - what a future `hreflang`/URL-locale-segment detection
pass would supply for one observed translation.

## build_i18n_inventory

ICU MessageFormat's own shape (point 3): `{message_key: {locale:
translated_string}}`. Two variants sharing one `message_key` accumulate
into the same entry - every observed locale is kept, not just the
source one.

## I18nInventoryDocument

Registered so `manifest.json` can enumerate it as `status: "off"` - not
so it can actually run. There is no store method to call
`build_i18n_inventory` with.
