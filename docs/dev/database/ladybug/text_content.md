# database/ladybug/text_content.py

## module

`TextContent` - the non-interactive prose on a page, captured once per visit
alongside its components.

Why it is stored at all, given that no document renders a page's text
wholesale: it is the evidence half of two usability rules. `unexplained_disabled_controls`
asks whether any text sits within 120px of a disabled control, and that
question needs the text's geometry, not just its words. Without this table the
rule could only guess.

Relies on `self._ensure_page(...)` from `page.py`'s mixin through the MRO, same
as `component.py`.

## _ladybugtextcontentmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)` and
`self._ensure_page(...)`.

## record_text_content

One text node, created or refreshed. Keyed by `(page_url, path)` through
`component_id` - the same key `Component` and `Container` use, because all
three are "a thing at a selector on a page" and a shared key means a shared
`_ensure_page` path.

## record_text_contents

One `UNWIND` per page visit rather than a round-trip per node. A prose-heavy
page produces more text nodes than components, so this is the larger of the two
batches in practice.

## get_text_content_ledger

`{page_url: [{path, tag, text, visible, x, y, width, height}]}` for the whole
site.

Geometry comes along because proximity is the point: `usability.py` uses `x`/`y`
to decide whether a control has an explanation near it. Those coordinates are
measured at 800x600 with images blocked, which is fine for *relative*
proximity and is exactly why the same file's absolute-threshold rules are
absent - see `docs/dev/generators/master_document.md#_gaps`.

Whole-site and zero-argument, so it is memoized in `CachingGraphStore`.
