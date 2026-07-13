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
