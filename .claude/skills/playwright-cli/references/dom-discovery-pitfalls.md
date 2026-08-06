# DOM Discovery Pitfalls

Lessons from building Pragma's own autonomous crawler (`src/scrapers/playwright_scraper.py`) the
hard way, against real production sites. `playwright-cli`'s snapshot is built from the accessibility
tree, so it already handles most of this better than a naive `document.querySelectorAll` would -
but the underlying failure modes below are still real, still silent, and still worth checking for
explicitly when a snapshot looks sparser than the page actually is, or an interaction seems to do
nothing.

## "Nothing to click" usually means a custom widget, not an empty page

Modern component libraries (Radix, shadcn/ui's Command/cmdk, MUI, Headless UI) build listbox
options, menu items, tabs, and custom checkboxes/radios/switches out of `<div>`/`<li>` with an ARIA
`role`, not a real `<button>`/`<input>`. A real crawl opened a searchable shop-picker combobox with
22 real, clickable options - every one of them a `<div role="option">` - that a naive
`button, a, input, select, textarea` query missed entirely, leaving nothing to act on but the
trigger that had already been clicked.

If a snapshot after opening a dropdown/menu/combobox looks emptier than what's visibly on screen,
check for these roles explicitly - `find`/`eval` see the raw DOM regardless of what the default
snapshot summarizes:

```bash
playwright-cli eval "document.querySelectorAll('[role=option]').length"
playwright-cli find --regex "role.*(option|menuitem|tab|combobox)"
```

## The last-resort case: no tag, no role, just `cursor: pointer`

Occasionally a clickable element has no semantic tag and no ARIA role at all - a styled `<div
onClick=...>` with zero accessibility markup. The one signal that survives even then is the
computed `cursor: pointer` style:

```bash
playwright-cli eval "Array.from(document.querySelectorAll('body *')).filter(e => getComputedStyle(e).cursor === 'pointer' && e.innerText?.trim()).map(e => e.innerText.trim())"
```

Exclude anything that's a container around (or an inner span of) an element you'd already find a
normal way - clicking either just achieves the same thing as the real target, redundantly.

## Combobox/searchable-dropdown: don't type first, look first

A search input opening alongside a list of options doesn't mean you need to search - if the option
you want is already visible, click it directly. Typing an unrelated guess into the search box
filters the visible list down (often to nothing), which reads as "the dropdown broke" when it
actually just did exactly what a search box does. Only type to narrow down a genuinely long list
you've confirmed doesn't already show what you want.

## A field's current value is the only reliable "did this work" signal

`playwright-cli fill e5 "user@example.com"` can silently be a no-op from the outside if the wrong
ref got resolved, or if a fill landed on a value that then got cleared by a UI event handler.
`type`/`fill` calls don't tell you whether the value actually stuck - the snapshot or a direct
`eval` does:

```bash
playwright-cli eval "el => el.value" e5
```

Check this before deciding a field is ready and moving on to submit, especially in a multi-step
flow. Don't assume `required` on an `<input>` reflects what a site actually needs, either - a real
site validated every field purely client-side (React state), with `required` false on all of them.
The field's live `.value` is verifiable from the DOM regardless of how (or whether) a site marks
required fields; treat "does this field currently show anything" as the signal, not the `required`
attribute.

## Generating a value for a field: use the label, not just the placeholder

A field can be fully labelled (`<label for="...">`) with no `placeholder` at all - relying on
placeholder alone to guess a field's purpose misses this constantly. Check for an associated label
before guessing:

```bash
playwright-cli eval "el => { if (el.id) { const l = document.querySelector(`label[for=\"${CSS.escape(el.id)}\"]`); if (l) return l.innerText; } return el.closest('label')?.innerText || ''; }" e5
```

Labels aren't always English - a real site's field read "Correo electrónico" (Spanish for "email"),
which a naive `"email" in label` check misses entirely. Strip accents / check for the target
language's actual vocabulary if the page isn't in English, rather than assuming English keywords.

## fill ≠ submit

Filling a value never submits a form by itself. A field showing the right value and a visible
"submit"-looking button doesn't mean you're done - you still need an explicit second action
(`press Enter`, or `click` the submit button/`type="submit"` element). Conversely, don't click a
submit-looking button while other fields on the page still show no value - check every visible
field's current value first (see above), not just the one you just filled.

## Session-token URLs aren't real routes

Some apps mint a fresh, random session/order URL on every page load (e.g. `/o/<random-id>`) rather
than having stable, meaningful routes. Treating every such URL as a distinct "page" to map produces
an ever-growing list of one-off URLs that will never be seen again - recognize the pattern (the
*shape* of the flow repeats identically across loads even though the URL never does) and reason
about the flow's structure, not the literal URL history.

## When something seems broken, inspect before concluding it's a tool problem

Before assuming a click/fill/tool-calling issue, drive the actual DOM directly and compare against
what the snapshot or a locator search returns:

```bash
playwright-cli snapshot
playwright-cli find "the text you expected to see"
playwright-cli eval "document.querySelector('SELECTOR')?.outerHTML"
```

Most "the interaction didn't work" cases turn out to be a real, findable DOM state - a
component-library widget with non-obvious markup, a field that didn't actually receive the typed
value, a submit that fired before a required field was filled - not a broken tool.
