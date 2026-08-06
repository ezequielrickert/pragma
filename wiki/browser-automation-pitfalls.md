# Browser Automation Pitfalls (Playwright, and generally)

Applies to any code that programmatically generates selectors and drives a real browser (or any
tool with a similar "resolve a target, then act on it" shape), especially when an LLM is choosing
*which* element to act on.

## Programmatically-generated selectors must be provably unique

**Symptom observed**: a DOM-path builder produced selectors like
`body > header > div > nav > div > a` for every link in a nav menu — because sibling `<a>` tags
with no `id` all share the exact same tag-name ancestry, this string was **identical** for
multiple different elements. Playwright's strict mode then refused to click it:
`strict mode violation: locator resolved to N elements`. This failure was *silent* to the caller
because of the next pitfall, so it looked like "the model keeps picking the same broken thing" when
it was actually "every click on this page was doomed to fail."

**Fix pattern**: when building a selector programmatically from DOM structure, always disambiguate
siblings that share a tag and have no id — add an `nth-of-type` (or `nth-child`) index computed
from the element's position among same-tag siblings:

```js
const gp = (e, p=[]) => {
    while (e.parentElement) {
        let seg = e.tagName.toLowerCase();
        if (e.id) {
            seg += '#' + e.id;
        } else {
            const siblings = Array.from(e.parentElement.children)
                .filter(c => c.tagName === e.tagName);
            if (siblings.length > 1) {
                seg += ':nth-of-type(' + (siblings.indexOf(e) + 1) + ')';
            }
        }
        p.unshift(seg);
        e = e.parentElement;
    }
    return p.join(' > ');
};
```

**How to catch this in review/testing**: for any generated-selector feature, write a test with
*deliberately identical* sibling elements (no distinguishing id/class) and assert the generated
selectors are (a) all distinct and (b) each one, used alone, resolves to exactly one element. Don't
test only with a page that happens to have unique markup.

## Never let a low-level action method swallow its own failure and return success-shaped data anyway

**Symptom observed**: `PlaywrightScraper.click()` wrapped the actual click in
`try/except Exception: print(warning)`, then unconditionally proceeded to `return self.get_state()`
— the *unchanged* page state. A failed click and a successful click that legitimately changed
nothing were indistinguishable to every caller above this method. This masked the selector-
uniqueness bug above for an entire debugging session, because the visible symptom was "the agent
picked the same thing repeatedly," which looks like a model/prompt problem, not an execution
failure.

**Fix pattern**: let failures propagate out of the action method. Only swallow a failure locally
if it is genuinely optional/best-effort and unrelated to whether the primary action succeeded —
e.g. waiting for `networkidle` *after* a click has already succeeded is fine to soft-fail on
(some pages never go idle), but the click itself must not be caught-and-ignored:

```python
def click(self, selector: str) -> PageState:
    self._page.click(selector, timeout=5000)          # let this raise - it's the real action
    try:
        self._page.wait_for_load_state("networkidle", timeout=5000)  # best-effort only
    except Exception as exc:
        print(f"Warning: page did not reach idle after clicking {selector}: {exc}")
    return self.get_state()
```

Then make sure the *orchestrator* catches the exception, records the **real error message** (not
a generic "it failed"), and treats it as a distinct, loggable outcome — see
[debugging-agent-systems.md](debugging-agent-systems.md) on why the raw error text matters.

## An element can resolve correctly but still not be clickable: visibility vs. presence

**Symptom observed**: after fixing selector uniqueness, a *new* failure appeared:
`element is not visible`, with Playwright's log showing the locator resolved to exactly one real
element, then timing out waiting for it to become visible. This is normal for dropdown/mega-menu
submenu items — present in the DOM the whole time, but CSS-hidden (`visibility:hidden`, a
collapsed/zero-height container) until a parent element is hovered or focused.

**Fix pattern**: a normal `click()` intentionally refuses to click something it can't see — that's
usually correct default behavior. When the failure reason is specifically visibility (not a
strict-mode violation, not a detached element, not "not found"), retry once with `force=True`,
which bypasses the visibility/actionability checks and dispatches the click directly:

```python
try:
    self._page.click(selector, timeout=5000)
except Exception as exc:
    if "not visible" not in str(exc):
        raise
    self._page.click(selector, timeout=5000, force=True)
```

Don't make `force=True` the default for every click — it skips *all* actionability guarantees
(visible, stable, receives events), which can click something the real user could never interact
with. Use it as a targeted fallback for the specific "present but hidden" failure mode.

## Redirects mean the URL you request isn't the URL you end up at

**Symptom observed**: a link discovered as `http://example.com/x` (a stale/legacy href on the
page) redirected, after navigation, to `https://example.com/x/`. If your dedup/visited-tracking
key is the *originally requested* URL rather than the *canonical, post-navigation* URL, the
http:// variant never gets marked visited and stays "pending" forever — see
[graph-based-crawl-tracking.md](graph-based-crawl-tracking.md) for the full failure mode this
causes (an infinite loop between scheme variants of the same page).

**Fix pattern**: normalize URLs identically wherever you build a dedup/graph key — strip scheme,
trailing slash, and fragment at minimum. Do this in exactly one function, reused everywhere a URL
becomes a dictionary key, so there's no risk of two call sites normalizing differently:

```python
def _clean_url(self, url: str) -> str:
    cleaned = url.split("#")[0].rstrip("/")
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            return cleaned[len(prefix):]
    return cleaned
```

## "Nothing to click" usually means a custom-widget blind spot, not an empty page

**Symptom observed**: a discovery query of `button, a, input, select, textarea, [role="button"]`
found nothing new after opening a searchable shop-picker on a real site — even though the model had
correctly clicked the trigger and the widget had visibly opened. Direct inspection of the live DOM
found **22 real, clickable options**, every one a `<div role="option">` inside a Radix/cmdk
("Command") popover. The agent wasn't confused; the tool genuinely could not see most of the page.

**Why it happens**: modern component libraries (Radix, shadcn/ui's Command, MUI, Headless UI) build
listbox options, menu items, tabs, and custom checkboxes/radios/switches out of `<div>`/`<li>` with
an ARIA `role`, not a native interactive tag. `[role="button"]` alone only covers one such pattern.

**Fix pattern**: broaden the discovery selector to the whole family of interactive ARIA roles, not
just `button`:

```js
'button, a, input, select, textarea, ' +
'[role="button"], [role="option"], [role="menuitem"], ' +
'[role="menuitemcheckbox"], [role="menuitemradio"], [role="tab"], ' +
'[role="checkbox"], [role="radio"], [role="switch"], [role="combobox"]'
```

This is framework-agnostic (role-based, not tied to Radix/cmdk/MUI specifically) and directly
verifiable: reopen the widget and diff the discovered element count/list before vs. after.

## The last-resort case: no tag, no role, just `cursor: pointer`

Occasionally a clickable element has no semantic tag and no ARIA role at all — a styled
`<div onClick=...>` with zero accessibility markup. The one signal that survives even then is the
computed `cursor: pointer` style. Add it as a second-tier fallback, not the primary discovery path:

```js
// Exclude anything already caught by the primary selector, in either direction -
// a pointer-cursor wrapper around a real button is redundant with that button,
// and so is a real button's own inner span that just inherits cursor:pointer from it.
for (const el of document.querySelectorAll('body *')) {
    if (semanticSet.has(el)) continue;
    if (el.closest(primarySelector)) continue;   // ancestor already covered
    if (getComputedStyle(el).cursor !== 'pointer') continue;
    if ([...el.querySelectorAll('*')].some(c => semanticSet.has(c))) continue; // descendant already covered
    // candidate
}
```

Both exclusion checks matter — without the ancestor check, a real `<button>`'s inner `<span>`
(which inherits `cursor: pointer`) shows up as a spurious duplicate target for the same click.

**Known, deliberately unimplemented gap**: neither pass finds elements inside an *open shadow
root* — `document.querySelectorAll` doesn't pierce shadow boundaries. Not fixed speculatively, since
no site actually hit this yet (Radix/cmdk render light DOM); if one does, the fix needs two things:
each shadow root needs its own `querySelectorAll` pass alongside `document`'s, and any path-builder
walking `element.parentElement` needs to continue via `element.getRootNode().host` when
`parentElement` is null but `getRootNode()` is a `ShadowRoot`.

## A form field's live `value` is the only reliable "did this work" signal — don't trust `required`

**Symptom observed**: a real, production site marked every form field's `required` HTML attribute
`false` — including ones that were, in practice, mandatory — because validation was done entirely
client-side (React state), never via native HTML constraint validation. Any logic gating "is this
form ready to submit" on the `required` attribute silently never gated anything on this site.

**Fix pattern**: don't infer "does this field matter" from markup that a site may not use correctly
or at all. Instead, track what you can always verify regardless of a site's validation approach:
does the field currently show a value?

```js
value: ['input', 'textarea', 'select'].includes(el.tagName.toLowerCase()) ? (el.value || '') : '',
```

An empty field after an attempted fill, or a field that was never filled at all, are both
observable facts about the live DOM — "does this field currently have a value" survives regardless
of how (or whether) a site marks required fields.

## fill ≠ submit, and submitting before a form is actually filled is its own bug

Filling a value never submits a form by itself — a separate action (Enter, or clicking the submit
control) is required. The less obvious failure mode discovered in practice was the *opposite*
direction: an agent clicked a visible "submit"-looking button while another required field on the
same page still showed no value, and the page responded with a burst of new content (a validation
state, 3 → 11 elements on the same URL) that then got misread as "there's nothing more to do here."
Before treating a submit-looking control as the next step, check every other visible fillable
field's current value first — not just the one just filled.

## Generating a value for a field needs the label, not just the placeholder — and isn't English-only

**Symptom observed**: a field with `placeholder=""` but a real, associated `<label for="...">Correo
electrónico</label>` (Spanish for "email") looked unlabelled to logic that only checked
`placeholder`, and separately, English-only keyword matching (`"email" in label`) missed it even
once the label text was available.

**Fix pattern**: check for an accessible label independently of placeholder — `label[for=id]`, a
wrapping `<label>`, or `aria-labelledby` — since a real form field is very often labelled with no
placeholder at all. When inferring a field's purpose from that label to generate a value, don't
assume the label is in English: strip accents/diacritics before keyword matching, and include the
target site's actual language's vocabulary alongside English if you know the site isn't
English-only, rather than only ever matching one language's words.
