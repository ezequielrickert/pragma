# Bug: many real components document as "Unnamed Element" / "Empty Element" in the new Component Catalog

## Load context first

Run `/wiki-context` before touching any code — this is squarely in its trigger conditions (browser-automation, DOM discovery/selector issues). Specifically read `wiki/browser-automation-pitfalls.md` in full: it already documents a closely related prior bug (the ARIA-role discovery gap where a whole family of custom-widget elements was invisible to discovery) and the fix pattern used there — broaden the discovery signal, don't rely on model cleverness — is very likely the same shape of fix needed here. Also skim `wiki/README.md`'s symptom table in case this exact pattern is already named there.

## Project context

Pragma is an LLM-driven web-crawling tool (`ARCHITECTURE.md` has the full picture) that drives Playwright to explore a site, tracks every discovered interactive component in a graph store (`GraphStore`/`Neo4jGraphStore`/`InMemoryGraphStore` — see `src/core/interfaces.py`, `src/storage/`), and recently gained a **Component Catalog** feature: a deterministic classification pass (`src/generators/component_classifier.py`) extracts type/options/state facts for every component, and an LLM narration pass (`SimplePRDGenerator._write_component_catalog` in `src/generators/prd_generator.py`, using `.gemini/skills/component-catalog-skill/SKILL.md`) turns those facts into a human-readable Markdown doc, written to `graph_logs/{slug}_component_catalog_{timestamp}.md`.

## The bug

A real run against `empanad.app` produced this catalog file (already in the repo, read it directly for full context): `graph_logs/empanad.app_component_catalog_20260807T183742Z.md`.

A large fraction of its entries are essentially content-free:

```
3. **Unnamed Element** - An unnamed interactive component. Currently active and ready to use.
6. **Empty Element** - Not interacted with.
19. **Empty Element (Repeated)** - An empty element with no visible text. - Interacted.
```

This isn't the LLM narration pass failing — it's being handed genuinely empty facts. The chain is:

1. `PlaywrightScraper._discover_components()` (`src/scrapers/playwright_scraper.py`) extracts each element's `text` via:
   ```js
   text: el.innerText.trim() || el.getAttribute('aria-label') || '',
   ```
2. `component_classifier.classify_component_type()` falls back to the generic label `"element"` when nothing more specific matches.
3. `SimplePRDGenerator._build_page_catalog_facts`/`_render_catalog_fact_line` pass whatever `text`/`component_type` exist straight into the narration prompt — if both are empty/generic, the model has nothing to describe and (reasonably) writes "Unnamed Element"/"Empty Element".

So the real bug is upstream, in step 1: **`el.innerText` is empty for a real, meaningful, interactive element.**

## Most likely root cause (verify, don't assume)

`el.innerText` respects rendering/CSS visibility — it returns `""` for text that's present in the DOM but visually hidden (e.g. `display:none`, `visibility:hidden`, `width:0;overflow:hidden`, or the common `sr-only`/`visually-hidden` accessibility utility class). A very common accessible-icon-button pattern is:

```html
<button aria-label="">
  <svg>...</svg>
  <span class="sr-only">Add flavor</span>
</button>
```

If the button itself has no `aria-label` (some sites only rely on the visually-hidden span, or set `aria-label` on the wrong element), `innerText` returns `""` for the whole button even though a sighted screen-reader user (and `textContent`) would see real text. `el.textContent` does NOT respect visibility and would very likely recover this text.

This needs verification, not blind replacement — `textContent` also picks up text from elements that are `display:none` for reasons that aren't accessibility (e.g. a genuinely hidden duplicate/template node), which could reintroduce noise. Confirm on the actual site (`empanad.app`, and ideally 1-2 other sites already crawled in this repo — check `progress_logs/`/`graph_logs/` for prior runs, e.g. `mapadeprofesionales.com`) by:
- Running Playwright against the live/stuck page and inspecting the actual DOM of a component that shows up as "Empty Element" in the catalog (cross-reference its `path` selector from `graph_logs/empanad.app_components_20260807T183742Z.json`, the raw ledger written the same run — it has `text`/`tag`/etc. per component path, so you can find the exact selector and inspect it directly).
- Checking whether the element has a `title` attribute, an `alt` on a child `<img>`, an `aria-labelledby` reference, or an SVG `<title>` child — any of these are also legitimate fallback label sources currently not checked at all.

## Also check: is "disabled" over-reported, or genuinely correct?

Several entries are legitimately `disabled` (e.g. "Finalize Order Button (Disabled)" before the form is filled) — that's very likely correct site behavior, not a bug. Don't assume it needs fixing; verify against the live site whether these really are disabled at that point in the flow before changing anything related to `disabled` detection.

## What to fix

1. In `PlaywrightScraper._discover_components()`'s JS (the `text:` line, plus wherever `getLabel()` is defined in the same script), broaden the label-extraction fallback chain — likely order: `innerText.trim()` → `aria-label` → `aria-labelledby` resolved → `title` attribute → child `<img alt>` → SVG `<title>` → `textContent.trim()` as a last resort (accepting some noise risk, since at that point *something* is better than "Unnamed Element"). Match the existing code's style: it already has a `getLabel(e)` helper doing a similar multi-source fallback for form-field labels specifically — this component-wide text fallback should follow the same pattern/spirit, not be a one-off special case.
2. Consider whether `component_classifier.classify_component_type` and `_render_catalog_fact_line` should surface *something* (e.g. the raw CSS path, or "no accessible label found") when text is still empty after the broadened fallback, so a genuinely-unlabeled element in the catalog reads as "this really has no discoverable label" rather than looking identical to a labeling bug.
3. Add/extend tests: `tests/test_imports.py` already has PlaywrightScraper-driven tests (search for `PlaywrightScraper` usage) — add a real small HTML fixture (icon button + visually-hidden span, no aria-label) and assert discovery now recovers the text. Also check whether `tests/test_component_classifier.py`'s fixtures need a case for "no text, no role, falls back to something better than 'element'".
4. Re-run against `empanad.app` (or a scripted/fixture equivalent) and confirm the catalog no longer shows "Unnamed Element"/"Empty Element" for components that have real, recoverable labels — only for ones that genuinely have none.

## After fixing

Use the `/wiki-update` skill to record this as a new entry (or an update to the existing "'Nothing to click' usually means a custom-widget blind spot" section) in `wiki/browser-automation-pitfalls.md` — this is the same general lesson (discovery signal too narrow) applied to *label extraction* instead of *element discovery*, and is exactly the kind of "looked like X, was actually Y" pattern that wiki exists to capture.

## Evidence files to read first

- `graph_logs/empanad.app_component_catalog_20260807T183742Z.md` — the buggy output
- `graph_logs/empanad.app_components_20260807T183742Z.json` — the raw per-component ledger from the same run (has real `text`/`tag`/`path` per component — cross-reference against the catalog's "Empty Element" entries to find their exact selectors)
- `src/scrapers/playwright_scraper.py` — `_discover_components()`, especially the `getLabel()` helper and the `text:`/`role:`/`attributes:` fields in the returned mapping
- `src/generators/component_classifier.py` — `classify_component_type()`
- `src/generators/prd_generator.py` — `_build_page_catalog_facts`, `_render_catalog_fact_line`, `_write_component_catalog`
- `.gemini/skills/component-catalog-skill/SKILL.md` — the narration instructions (not the bug, but useful context for what the model is told to do with the facts it's given)
