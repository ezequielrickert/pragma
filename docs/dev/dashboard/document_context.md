# `dashboard/document_context.py`

## module

What each registered document actually is and what it's typically used for, plus one short
example of its real shape (ticket #145, map #142) - beyond `document.purpose`'s one-line summary,
which doesn't tell a reviewer who doesn't already know this pipeline's own vocabulary what
"Evidence Log" or "Change Log" actually mean.

Mirrors `dashboard/renderer_audit.py`'s own shape: one lookup table keyed by `DOCUMENT_REGISTRY`
name, a `_for(name)` accessor that degrades gracefully (`None`, not a placeholder) for an unlisted
name, and a completeness test (`tests/test_document_context.py`) checking every registered name
has a real entry - the same "stays honest by test, not by someone remembering to update a second
file" discipline `tests/test_dev_docs.py` already enforces for `docs/dev/` itself, deliberately,
so this table doesn't go stale the way `docs/explicativos/` did.

`asyncapi`/`i18n-inventory`/`browser-support-matrix` get no fabricated example - `generate()`
always raises for all three today (no capture instrumentation exists yet), so `_NOT_YET_PRODUCED`
says so honestly rather than inventing a content shape these documents never actually produce.

## DocumentContext

`explanation` (what it is / what it's for) and `example` (a short, real-shaped snippet) - the two
fields a document's detail page renders beyond its own `purpose`.

## context_for

`CONTEXT_BY_NAME.get(name)` - `None` for an unlisted name, so a caller renders no "About this
document" section at all rather than a placeholder.

## render_context_section

The one real "About this document" HTML rendering, shared verbatim by `generic_template.py` and
`redoc_renderer.py` - kept here rather than duplicated in both, since the two copies were
byte-for-byte identical (a real DRY violation caught during this ticket's own quality pass, not
just the same kind of small, per-file duplication the breadcrumb pattern in ticket #143 already
accepted).
