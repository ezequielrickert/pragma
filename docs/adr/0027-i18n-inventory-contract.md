# `i18n-inventory` layers locale variants over content-inventory, absent until detected

**Status**: accepted

Checked the codebase: zero locale/`hreflang`/`Accept-Language` handling exists anywhere today, the
same situation `asyncapi` (ADR-0018) found for WebSocket/SSE traffic. The ticket's three open points
resolve the same way that ticket's did — lock the contract now, ship nothing until detection exists
— plus the cross-reference pattern `glossary`/`content-inventory` already established for exactly
this kind of overlap.

Decided, resolving the ticket's three open points:

**1. Detection and Presence.** `hreflang` tags are the primary signal — explicit, declarative,
present in page HTML, cheap to detect via DOM inspection. URL locale segments (`/es/`, `/en-us/`)
are a secondary fallback when `hreflang` is absent but the URL structure suggests localization.
`Accept-Language`-driven content variation is out of scope for v1: detecting it would require the
crawler to make extra requests with varied headers just to probe for hidden localization, a more
invasive mechanism than either of the other two signals justifies without evidence it's needed.
`i18n-inventory.json` is entirely **absent** — no file — until this detection exists, the same
posture `asyncapi` locked (ADR-0018), governed by `manifest.json`'s `status` field (ADR-0015).

**2. A Layer, Not a Third Copy Mechanism.** `i18n-inventory` doesn't independently re-capture copy —
it's a locale-variant layer over `content-inventory`'s already-captured strings (ADR-0025) and,
where a domain concept has locale-specific renderings, `glossary`'s terms (ADR-0020). Same
cross-reference-not-duplication pattern those two already established for their own overlap.

**3. Every Observed Variant, Not Source-Only.** Captures every locale variant actually observed,
verbatim — not just the source locale. The ticket's own stated purpose is enabling a rebuild to
translate *from* this document; discarding already-produced professional translations in favor of
source-only strings would throw away real, reusable translation work for no benefit. Structured as
ICU MessageFormat's natural shape: one message key mapping to `{locale: translated_string}` per
observed locale.

Wayfinder ticket: [i18n-inventory: lock ICU MessageFormat contract for multi-language sites](https://github.com/ezequielrickert/pragma/issues/91),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
