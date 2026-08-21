"""`i18n-inventory.json` - locked ready for locale variants no
instrumentation observes yet, docs/adr/0027.

**Entirely absent today, on purpose.** Zero `hreflang`/URL-locale-segment
detection exists in this crawl - the same situation `asyncapi` found for
WS/SSE traffic (ADR-0018). `I18nInventoryDocument.generate` raises rather
than returning an empty-but-valid document: there is no partial document
worth reserving a field on here either, only real work to do once
detection instrumentation exists as its own future effort.
`run_document_pipeline`'s existing "a generator that fails is logged and
skipped" degradation is what turns that raise into `manifest.json`'s
honest `status: "off"` - no second on/off mechanism.

**What this ticket actually builds**: the ICU MessageFormat `{message_key:
{locale: translated_string}}` catalog shape, as a real, pure, unit-tested
function over synthetic `LocaleVariant` fixtures - ready for whenever a
future detection pass can supply the real thing.
`build_i18n_inventory` is not wired to `generate()` at all today; there
is no store method to call it with.

**A layer, not a third copy mechanism** (point 2). `message_key` cites
`content-inventory`'s own `component_ref` or `glossary`'s `TERM-<hash>` -
whichever the observed text corresponds to - never a second,
independently-captured copy of the string itself. Same
cross-reference-not-duplication pattern those two documents already
established for their own overlap (ADR-0025 point 3).

**Every observed variant, not source-only** (point 3). A message key can
map to more than one locale in the catalog - a professional translation
already produced by the site is real, reusable evidence for a rebuild to
translate from, not something to discard in favor of only the source
locale's own string.

Details: docs/dev/generators/i18n_inventory.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Sequence

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY


@dataclass(frozen=True)
class LocaleVariant:
    """What a future `hreflang`/URL-locale-segment detection pass would
    supply for one observed translation - synthetic today; no real
    capture produces this yet.
    Details: docs/dev/generators/i18n_inventory.md#localevariant
    """

    message_key: str
    locale: str
    translated_text: str


def build_i18n_inventory(variants: Sequence[LocaleVariant]) -> Dict[str, Any]:
    """ICU MessageFormat's natural shape (ADR-0027 point 3): one message
    key mapping to `{locale: translated_string}` per observed locale, not
    per site - two variants sharing one `message_key` accumulate into the
    same entry rather than the second overwriting the first.
    Details: docs/dev/generators/i18n_inventory.md#build_i18n_inventory
    """
    catalog: Dict[str, Dict[str, str]] = {}
    for variant in variants:
        catalog.setdefault(variant.message_key, {})[variant.locale] = variant.translated_text
    return catalog


@DOCUMENT_REGISTRY.register("i18n-inventory")
class I18nInventoryDocument(DocumentGenerator):
    """Registered so `manifest.json` can enumerate it as `status: "off"`
    (ADR-0027 point 1) - not so it can actually run. `generate` always
    raises; there is no store method to call `build_i18n_inventory` with,
    since no capture instrumentation exists to have written one against.
    Details: docs/dev/generators/i18n_inventory.md#i18ninventorydocument
    """

    name = "i18n-inventory"
    title = "i18n Inventory"
    purpose = (
        "Locale variants of content-inventory's copy and glossary's terms, ICU MessageFormat-shaped - "
        "absent until hreflang/URL-locale-segment detection exists."
    )

    def generate(self, request: DocumentRequest) -> str:
        raise NotImplementedError(
            "i18n-inventory.json has no locale-detection instrumentation yet (docs/adr/0027 point 1) - "
            "hreflang/URL-locale-segment detection is a future effort, out of this map's scope."
        )
