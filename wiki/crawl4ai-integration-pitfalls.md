# crawl4ai Integration Pitfalls

Applies when driving [crawl4ai](https://github.com/unclecode/crawl4ai)'s `AsyncWebCrawler` for
custom interaction (hooks, `js_code`, `session_id` reuse) rather than just its built-in
markdown/extraction pipeline - specifically, any code that issues a click/fill via `js_code` and
then needs to know, precisely, whether that action succeeded and whether it caused navigation.
crawl4ai wraps Playwright, so [browser-automation-pitfalls.md](browser-automation-pitfalls.md)'s
lessons about the underlying DOM/selector layer still apply underneath this - this doc is about the
extra layer of gotchas crawl4ai's own abstraction introduces on top, found while building Pragma's
mechanical (non-LLM) crawl4ai-driven interaction loop (`spiders/`).

## A click/fill that triggers real navigation must stop that page's work immediately, not continue to the next action

**Symptom observed**: a loop that mechanically clicks every discovered interactive element on a
page, one after another, started failing almost everything on a page with an early `<a href>` link
in its element list - a cascade of `"element not found"` errors for elements that definitely existed
moments earlier. Looked like a wave of unrelated broken selectors.

**Why it happens**: the `<a href>` click genuinely navigated the browser's live page away. A generic
per-element `try/except` around each interaction caught the resulting failure, logged it as "this
one element failed," and moved on to the next element in the same pass - except the page that next
element's selector was built for no longer exists. Playwright/crawl4ai raises `"Execution context
was destroyed, most likely because of a navigation"` for any `evaluate()` issued against a page
that's mid-navigation or already gone. This is the same root shape as
[browser-automation-pitfalls.md](browser-automation-pitfalls.md)'s "never let a low-level action
method swallow its own failure and return success-shaped data anyway" - except here the swallowed
signal isn't a bad click, it's the *entire remaining plan for this page* having become invalid mid-flight.

**Fix pattern**: the moment an interaction's resulting URL differs from the page currently being
worked on, stop - don't attempt further elements from that pass. Queue the page for a follow-up
visit instead of continuing or marking it done:

```python
if new_key != page_key:
    self._enqueue(new_state.url)      # follow up later, don't chase it inline
    result.interrupted_by_navigation = True
    break                              # do NOT continue to the next frontier item
```

Convergence is guaranteed as long as every *attempted* element - success or failure, including the
one that caused the navigation - gets marked as done, so a follow-up pass makes real progress on
whatever's left rather than re-triggering the same navigation forever.

**General lesson**: a live browser session has its own identity/liveness state (which page is
currently loaded) that action-issuing code must track exactly as carefully as URL/component
identity is already tracked elsewhere per
[graph-based-crawl-tracking.md](graph-based-crawl-tracking.md). "Did my last action move me to a
different page" is a fact that has to gate whether the *next* action is even meaningful - it can't
be left to a generic per-action exception handler that treats every failure as equally recoverable.

**Update — the follow-up-pass requeue itself must use the *resolved* URL, not whatever literal
string this visit was originally requested with:** the fix above ("queue the page for a follow-up
visit") is correct, but a second, easy-to-miss bug hides in *which* string gets re-queued for that
follow-up. Confirmed live on empanad.app: its bare entry URL (`https://empanad.app`) redirects to a
brand-new `/o/<hash>` session on *every single request*, not just the first. The follow-up-pass
requeue was re-submitting the *originally-requested* literal string (the bare, redirecting URL) -
so every follow-up pass minted an entirely new, unrelated session instead of returning to the one
whose frontier still wasn't drained, silently abandoning it and burning a real, extra network fetch
each time. A scripted-fake regression test proved just how bad this gets on a page whose own
component set keeps triggering the same interrupted-navigation branch: the bare URL was re-requested
9 times in one small, bounded test scenario alone - in a real, larger crawl this reads exactly like
"the same page keeps getting re-scraped" and "there's a lot of fetch overhead," not like a
navigation-identity bug, because nothing errors and nothing looks obviously wrong from the outside.

**Fix pattern**: capture the *resolved* URL (`PageState.url` - already redirect-following, since
`Crawl4AICrawler._resolved_url` reads `redirected_url` first) once, at the top of the visit, and
requeue *that* on an interrupted pass - never the literal string this particular call happened to be
invoked with:

```python
state = await crawler.discover_page(url, session_id=url)
resolved_url = state.url  # NOT `url` - state.url already followed any redirect

...
if interrupted_by_navigation:
    url_frontier.put_nowait(resolved_url)   # re-request the concrete destination directly,
                                              # not the (possibly redirecting) original request
```

For an ordinary, non-redirecting site this is a no-op (`resolved_url == url`), so the bug is
invisible on the fixture sites this project's test suite is otherwise built on - it only surfaces on
a real site whose entry point redirects to something session-scoped, which is exactly why it slipped
through until read against a real debug log. **How to catch this in review/testing**: don't just
assert an interrupted pass gets *a* follow-up visit - assert *which literal URL* that follow-up
requests, against a fake whose redirect target changes on every call. A fake that always redirects to
the *same* fixed destination can't distinguish "requeued the resolved URL" from "requeued the
original request" - they'd look identical.

**Update — the "must stop immediately" contract above only covers the *success* path; the failure
path needs the exact same care, and a second, separate gap sits behind it:** confirmed live on
austral.edu.ar: a real crawl got stuck on a single page for 90+ minutes - one `_visit_page()` call
that never returned across 70+ `arun()` attempts, each slower than the last (34s growing past 600s).
Reading the raw debug log (not guessing) showed why: a persistent, site-wide nav-menu link (present
on every page of the site) was clicked; the click physically navigated the browser to a large,
slow-to-settle destination page; reading back this project's own success marker (a plain
`page.evaluate()`, no explicit timeout override) then hit *Playwright's own default action timeout*
against that slow page - 30000ms, a different knob entirely from this project's own `page_timeout`
(which bounds the raw `goto()`/`js_only` fetch, an earlier phase). Because the failure surfaced as a
plain exception with no `resulting_url` at all, the except-block built for a broken/stale selector
(the fix earlier in this doc) had no way to know a navigation had actually happened - it just marked
that one path interacted and kept attempting the *rest* of that page's frontier (283 components)
against a live browser page that had already moved on, each one doomed the same way.

**Why the follow-up-pass resume didn't save it**: even once that doomed pass finally exhausted its
frontier and got resumed via the mechanism above, the resumed page's own fresh `discover_page()`
re-encountered the *identical* nav link under a brand-new selector path - a common pattern for
persistent site-wide nav/mega-menu widgets built with a JS templating framework that assigns a fresh
generated id on every render. Path-based "already interacted" tracking can never recognize that as
the same link twice, so the whole failure repeated from scratch on every single resume, unbounded -
the same root shape as [graph-based-crawl-tracking.md](graph-based-crawl-tracking.md)'s
stale-selector-remap entry (a `path` that churns across reloads needs a content-based identity to
survive it), just one level up: across separate page *reloads*, not within one remount.

**Fix pattern**: two parts, deliberately not a retry-count cap (a cap doesn't explain *why* it loops,
it just hides the symptom under a bigger number).

1. On any failure that isn't the already-handled "element not found" case, check whether the live
   session navigated anyway - reuse `resync()` (the same no-op-`js_code` re-discovery the
   stale-selector fix already uses) purely to read the session's *current* URL:

   ```python
   if not _is_element_not_found(exc):
       current = await crawler.resync(url, session_id)
       if clean_url(current.url) != page_literal:
           # A silently-missed navigation, not an ordinary broken selector -
           # treat it exactly like the success branch's own navigation case.
           enqueue(current.url)
           interrupted_by_navigation = True
           break
   ```

2. Remember *which* interaction, by content identity (`_component_identity` - tag/role/name/form/text,
   the exact tuple the stale-selector fix already established, reused here for a different purpose)
   is now *proven* to navigate away from a given canonical page, keyed per page - checked when
   building every future frontier for that page, regardless of what path the same logical component
   shows up under next time:

   ```python
   known_navigators = navigation_trigger_identities.get(page_key, set())
   frontier = [
       c for c in components
       if not is_interacted(page_key, c["path"]) and identity(c) not in known_navigators
   ]
   ```

   A persistent, site-wide element always leads to the same real destination regardless of which page
   it's clicked from or what selector it renders with today, so once one click proves that fact, it's
   correct to never offer that exact logical interaction again for that page - converging in two
   resumes (learn it, then skip it) instead of never converging at all.

**Update — the fix above shipped and worked, then the exact same site still looped, because the new
recovery shared a guard flag with an older, unrelated one:** confirmed by reading a *second* live
debug log from the same site, taken after the fix above had already landed. The symptom looked
identical to the original bug (the same `before_retrieve_html` url/session_id mismatch, repeating for
~20 minutes) - which made it briefly look like the fix simply hadn't worked. Reading the log closely
showed otherwise: the *very first* navigating click in the sequence succeeded cleanly and *was*
correctly learned - proving the fix's core mechanism was right. Every failure after that was a
different story: the new "check for a silent navigation" recovery was gated by
`stale_resynced_since_success` - the *same* boolean the pre-existing, unrelated stale-selector-remount
resync already used for its own "only once per failure streak" throttle. The two guards answer
genuinely different questions ("is the rest of my frontier built from a now-stale snapshot" vs. "did
*this* failing click silently navigate away") and can both legitimately need to fire, for different
components, within one pass - but sharing one flag meant an earlier, completely unrelated "element not
found" failure elsewhere in the pass consumed the guard, so a *later*, different component's
silent-navigation check never ran at all. That component's failure was swallowed as an ordinary error,
its content identity was never learned, and it kept getting re-discovered and re-failing identically on
every future resume - with no error and nothing looking obviously broken from the outside.

**Fix pattern**: split the shared guard into two independent booleans, each reset only on the pass's
own next successful interaction, each consulted only by its own recovery branch:

```python
stale_resynced_since_success = False           # guards the stale-selector resync, only
silent_navigation_checked_since_success = False # guards the silent-navigation check, only

# ... on a stale-selector ("element not found") failure:
if is_element_not_found(exc) and not stale_resynced_since_success:
    stale_resynced_since_success = True
    ...  # resync and remap, as before

# ... on any OTHER failure - independent guard, not gated by the one above:
elif not silent_navigation_checked_since_success:
    silent_navigation_checked_since_success = True
    ...  # check for a silent navigation, as before

# ... on a successful interaction, reset BOTH:
stale_resynced_since_success = False
silent_navigation_checked_since_success = False
```

**General, reusable lesson beyond this one instance**: when adding a second recovery to a function
that already has a "run this recovery at most once per streak" guard for a *different*, pre-existing
recovery, don't reach for that existing guard just because both recoveries happen to live in the same
`except` block and both want the same "not too often" throttling. Two different questions asked in the
same place need two different flags, or the older one silently starves the newer one the moment both
conditions occur in the same pass - and because each recovery works perfectly in isolation, this
specific composition bug is easy to miss in review and looks, from the outside, exactly like "the fix
didn't work," when the fix is actually fine and the bug is in what it now shares state with.

**Update — a *third*, structurally different root cause in this same family: crawl4ai's own anti-bot
heuristic can discard a signal this project's own code already correctly captured, moments earlier:**
confirmed live on austral.edu.ar - one `_visit_page()` call still running after 40+ minutes and 40+
identical failures when found. Not a stale selector (the first fix above), not a slow-to-report real
navigation (the second), but something new: `async_webcrawler.py::is_blocked` runs *after every hook*
- including `on_execution_ended`, where this project's own `action_result` (see the "single-script
act-then-mark-success" entry below) had *already* correctly recorded `success: True, navigated: True`
for a genuinely successful navigating click - and unconditionally vetoes the whole `arun()` call's
top-level `result.success` to `False` whenever the *resulting* page's content structurally looks like a
block/challenge page (no `<body>` tag, near-empty content, etc.). `Crawl4AICrawler._interact()` only
ever checked that later, blunter `result.success` and raised unconditionally on `False` - discarding
the earlier, more specific, already-correct navigation signal it had itself just captured. Confirmed
directly (not just inferred from the live log): a real local-fixture test navigating to a deliberately
`<body>`-less HTML page reproduced the exact `"Blocked by anti-bot protection: Near-empty content..."`
`RuntimeError` even though the click itself worked perfectly.

**Why this cascades into the exact same "many minutes stuck" symptom as the first fix above, even
though the direct cause is different**: the resulting `RuntimeError` doesn't match `_is_element_not_found`,
so it falls to the silent-navigation check (`_handle_possible_silent_navigation` → `resync()`) - but
`resync()` is *itself* just another interaction against the same "blocked-looking" destination, so it
hits the *identical* anti-bot veto and *also* raises, caught by `_check_for_silent_navigation`'s own
try/except, returning `None` (inconclusive). The one check built to resolve "did we silently navigate"
is exactly the one guaranteed to also fail here - and since it only runs once per failure streak, every
remaining frontier item then gets attempted anyway, each independently failing the same way.

**Fix pattern**: read this project's own, earlier signal before trusting a later, blunter one -
`action_result` was captured *before* the anti-bot check could veto anything, so it's still trustworthy
even when `result.success` isn't:

```python
data = self._stash.pop(session_id, {})
action_result = data.get("action_result")
action_succeeded = bool(action_result and action_result.get("success"))

if not result.success and not action_succeeded:
    raise RuntimeError(f"crawl4ai interaction failed for {url!r}: {result.error_message}")
if not action_succeeded:
    raise RuntimeError(f"interaction failed on {url!r}: {(action_result or {}).get('error', '...')}")
# else: proceed normally - redirected_url is untouched by the anti-bot check
# (only success/error_message are), so PageState.url still resolves correctly.
```

**Defense-in-depth, for whenever the ambiguity genuinely can't be resolved**: even with the fix above,
a session can still be in a state where *both* the real interaction *and* its own verification attempt
are doomed (e.g. the destination's `domcontentloaded` event never fires at all - see this doc's own
"some config flags..." entry below for the matching `page.set_default_timeout()` fix for *that* half).
For exactly that case, a circuit breaker independent of the existing "once per streak" guards - not a
blanket retry-count cap on the whole page, just a bound on *consecutive, unexplained* failures within
one pass:

```python
consecutive_unexplained_failures += 1
if consecutive_unexplained_failures >= _MAX_CONSECUTIVE_UNEXPLAINED_FAILURES:  # 3
    result.interrupted_by_navigation = True  # honest "not finished", not a confirmed navigation
    break
```

Give up on the pass rather than grinding through the rest of a large frontier one interaction-timeout
at a time when nothing is converging - the same "decline redundant/unproductive work" calculus
[graph-based-crawl-tracking.md](graph-based-crawl-tracking.md) already applies elsewhere, here scoped
to "this session looks dead" rather than "this exact thing was already tried."

## `AsyncCrawlResponse.url` is not the URL you ended up at - `redirected_url` is

**Symptom observed**: even after fixing the navigation-interruption bug above, a click that had
demonstrably navigated the browser (confirmed by the newly-discovered page's own different set of
components) still produced a result whose `.url` was identical to the pre-click URL. Every
"did this navigate" check built on that field silently never fired.

**Why it happens**: reading crawl4ai's own source (`async_crawler_strategy.py`) shows
`AsyncCrawlResponse.url` is set once, early, from the literally-requested URL string, and never
updated regardless of what actually happened during the crawl. A *separate* field,
`redirected_url`, is explicitly re-read from the live `page.url` right before the function returns -
crawl4ai's own source comments this is specifically to capture JS-driven navigation. `.url` is the
obviously-named, natural field to reach for, and it returns plausible-looking, silently wrong data
instead of erroring - exactly the kind of trap
[debugging-agent-systems.md](debugging-agent-systems.md)'s "read the raw, literal output text"
checklist item exists to catch: the bug wasn't visible from the field's name or type, only from
comparing it against ground truth (the newly-discovered components) and then reading crawl4ai's
actual source.

**Fix pattern**: always read `redirected_url` first when building a page-state object from a
crawl4ai result, falling back to `.url` then the originally-requested URL:

```python
url=getattr(result, "redirected_url", None) or result.url or url,
```

**Update — that same resolved/redirected URL is the *wrong* key for a debug artifact that must stay
per-session:** `redirected_url` is exactly the right value for a `PageState`'s own identity (what page
did this land on) - but a debug-log side artifact (crawl4ai's markdown snapshot of the page, saved to
disk once per visit for later inspection) is a *different* question: "which specific visit produced
this content," not "what page is this." Confirmed live on `mapadeprofesionales.com`: many different
pages' own "log in" links all redirect to the identical resolved destination, so keying the snapshot
file by `redirected_url` collapsed every one of those visits onto the same filename - each overwriting
the last, discarding real information (this is also the visible symptom that led to
[graph-based-crawl-tracking.md](graph-based-crawl-tracking.md)'s "not every path onto the frontier
goes through the dedup guard" entry, which fixes the deeper concurrency bug behind it). The
`page_concurrency`-safety fix there stops two of those sessions from ever running *at the same time*,
but even fully sequential, one-after-another visits to the same resolved destination still overwrite
each other's snapshot with a resolved-URL key - fixed by keying the snapshot on the literal,
originally-requested URL (`session_id`, in this codebase's terms) instead, so each distinct
session/request keeps its own separate, inspectable file even when several of them converge on the
same final destination:

```python
# Wrong for a per-visit artifact: collapses every session that redirects
# to the same place onto one file, silently losing all but the last write.
save_snapshot(redirected_url, content)

# Right: one file per session/request, regardless of where it resolved to.
save_snapshot(session_id, content)
```

## A single-script "act then mark success" pattern loses its own success signal on a navigating action

**Symptom observed**: a click/fill implemented as one JS IIFE - perform the action, then set a
separate `window.__marker__` variable on the next line to report success - came back with the
marker simply unset (not `false`, not an error, just never assigned) whenever the action itself
caused navigation.

**Why it happens**: if the action destroys the execution context (a navigating click), the script
never reaches its own next line, on neither the old page nor the new one. Treating "marker never
got set" as a failure is a mistake in the *opposite* direction from a swallowed error - it's a
false negative on an action that actually succeeded.

**Fix pattern**: crawl4ai's own `robust_execute_user_script` already anticipates this internally -
it catches the destroyed-context error, waits out the new page's `load`/`networkidle` state, and
returns a success result *before* any `on_execution_ended`/`before_retrieve_html` hook fires. That
result is passed to `on_execution_ended` as its `result` kwarg. Use it as the authoritative fallback
specifically when your own marker comes back unset, rather than defaulting to failure:

```python
if isinstance(marked, dict):
    action_result = marked                       # our own script's explicit signal
else:
    exec_success = bool(result) and result.get("success", False)
    action_result = (
        {"success": True, "navigated": True} if exec_success
        else {"success": False, "error": (result or {}).get("error", "js_code did not run")}
    )
```

## `wait_for="css:body"` is satisfied by the pre-hydration shell, not by a rendered SPA

**Symptom observed**: a real crawl of a React SPA came back with 0 discovered components and 0
links, every single time - not a flake. `<title>`, meta description, and other `<head>` tags were
all populated correctly, which made the empty results look plausible at first ("maybe this page
really has no interactive content") rather than obviously broken.

**Why it happens**: `wait_for="css:body"` (or any condition checking for early-DOM elements) is
satisfied the instant the initial HTML document parses - before a client-side framework has
mounted anything. A server-rendered `<title>`/`<meta>` tag is present in that initial document; a
React/Vue app's actual buttons/inputs are not, since they're injected by JavaScript that runs
after hydration. Nothing about this fails or errors - `page.evaluate()` runs successfully, it just
runs too early, against a DOM that's real but not yet the page a human would ever actually see.

**Fix pattern**: give the page real settle time before discovery, not just a DOM-presence check.
Playwright's own `PlaywrightScraper` predecessor already established this (a `wait_seconds`
constructor parameter, applied after every navigate/click/fill) - the fix here is making sure a
rewrite onto crawl4ai actually carries that same discipline over, since crawl4ai's own `wait_for`
option answers a different question ("does this selector exist yet") than the one that matters
("has client-side rendering actually finished"):

```python
async def _before_retrieve_html(self, page, context, config, **kwargs):
    if self.wait_seconds:
        await asyncio.sleep(self.wait_seconds)   # let hydration/rendering finish
    ...  # now run discovery
```

Apply it before *every* discovery pass, not just the first navigation - a same-page interaction
that reveals new content (a popover, a lazily-rendered panel) needs exactly the same settle time
before re-discovery as the initial page load did.

**How to catch this in review/testing**: a synthetic fixture built as plain static HTML can never
exercise this path - it has no hydration delay to miss, so a test suite built entirely on such
fixtures (however thorough about DOM edge cases) will pass cleanly while this bug ships. Test at
least one real, JS-heavy site (or a fixture that deliberately renders its content via a delayed
`setTimeout`/`useEffect`-style script) as a dedicated regression case for "did discovery wait long
enough," separate from the DOM-structure edge cases static fixtures cover well.

**A gotcha when building that fixture**: don't make it *too* minimal. crawl4ai has its own built-in
anti-bot heuristic that outright refuses a page (`result.success = False`, error text
`"Blocked by anti-bot protection: Structural: minimal_text, no_content_elements,
script_heavy_shell"`) when the initial HTML has very little visible text and is mostly a `<script>`
tag - which a naive "empty div + setTimeout" fixture is. Give the fixture some realistic static
shell content (a heading, a paragraph) the way a real SPA's pre-hydration HTML often does anyway
(SEO copy, a loading message) - this sidesteps the heuristic and also makes the fixture a more
honest simulation of the real bug.

## A failed interaction needs its own re-sync path, not just the success path's

**Symptom observed**: on a real crawl of empanad.app (a Radix-UI-based order form), 134 of ~157
interaction attempts in one run failed `element not found`, all against ~20 selectors baked with
Radix's `useId()`-generated ids (`#radix-\:r0\:` … `#radix-\:rr\:`), identically on every distinct
order page visited. Once the failures started, `components` discovered on that page stayed flat for
the rest of the pass - no further genuine progress, just one doomed selector after another, each
costing a full `wait_seconds` round trip for nothing.

**Why it happens**: the mechanical interaction loop (`spiders/mechanical_loop.py`) already had a
same-page re-inventory/re-diff mechanism, but only on the **success** branch of each interaction - a
click/fill that changes the DOM without navigating re-discovers current state and diffs it for newly
revealed components (see [graph-based-crawl-tracking.md](graph-based-crawl-tracking.md)'s ghost-node
fix). The **failure** branch never did anything like that - it recorded the error and moved to the
next queued frontier item, still built from the pre-failure snapshot. If one interaction causes a
component-library subtree to remount (Radix reassigning `useId()`-based ids on a re-render), every
later frontier item belonging to that subtree carries a `path` that no longer resolves - and since
nothing between consecutive failures ever re-syncs, they fail in an unbroken chain, not just once.

**Fix pattern**: give the failure branch its own re-sync, gated to fire once per streak (not once per
failure, to avoid resync-storming a pass whose whole remainder is genuinely gone), and reconcile the
*remaining* frontier against the fresh snapshot by **content identity** (tag/role/name/form/text),
not by the very `path`/id a remount just invalidated:

```python
if _is_element_not_found(exc) and not stale_resynced_since_success:
    stale_resynced_since_success = True
    fresh_state = await crawler.resync(url, session_id)  # no-op js_code, re-discovers current DOM
    frontier[idx:], dropped = _remap_stale_frontier(frontier[idx:], fresh_state.components)
    # kept as-is if path still resolves; path swapped in if a fresh component matches by
    # (tag, role, name, form, text); dropped (recorded distinctly, not silently lost) otherwise
```

`resync()` itself is nothing new - it's the exact same `_interact()`/`on_execution_ended` machinery a
real click/fill already uses, just invoked with a no-op `js_code` that only sets the success marker.
The reusable lesson: **any two-outcome branch (success/failure) that shares a "state may have changed
under me" precondition needs the same re-sync discipline on both branches** - building it once on the
success path and assuming failures don't need it is exactly how a whole remounted subtree went
unrecovered instead of one bad selector.

## `capture_network_requests`'s response body is read on every capture, and its own body-read failure is silently absorbed into a different event type

**Symptom observed**: enabling `capture_network_requests=True` and reading back
`result.network_requests` worked correctly for ordinary JSON API responses, but a console line like
`[CAPTURE]. ℹ Error capturing response details for https://example.com/favicon-32.png: cannot access
local variable 'text_body' where it is not associated with a value` appeared for some responses -
confirmed live during a real crawl, not hypothetical. The request itself was still present in the
captured stream, just without a matching response/status.

**Why it happens**: reading crawl4ai's own source (`async_crawler_strategy.py`'s
`handle_response_capture`) shows every captured `"response"` event unconditionally calls `await
response.text()` and includes the full body under `event["body"]["text"]` - not just on request,
every single response gets its entire body read and held in memory. When that body-read itself fails
(a streamed/binary body, a response that's already been consumed), the inner `except` sets an unused
local and never assigns the variable the event dict actually references - so building that event
dict raises a `NameError`, caught by the *outer* `except`, which appends a `{"event_type":
"response_capture_error", ...}` entry instead of a normal `"response"` one. The net effect
(confirmed empirically, not just read from source): a response whose body crawl4ai couldn't decode
silently shows up as "no status available for this URL" to any consumer keying off `event_type ==
"response"`, with no indication *why* - and the request itself is always still there, whether or not
the outer NameError chain got tripped by it.

**Fix pattern**: two separate things to handle when consuming this stream:
1. Never assume every `"request"` event has a matching `"response"` event - join by URL and treat a
   missing match as "no status captured" (`None`), not an error of your own.
2. Explicitly handle `"response_capture_error"` as "the response arrived but its body/status
   couldn't be read" (leave status unset), distinct from `"request_failed"` ("the request never got
   a response at all" - a real network failure, with its own `failure_text`). Conflating the two
   loses the real distinction between "this call failed" and "this call succeeded but we couldn't
   read the reply."
3. If you have no use for response bodies (most consumers of "did this component trigger a
   request, with what status" don't), **never read `event["body"]["text"]` into anything you
   persist** - it's read into the raw event unconditionally by crawl4ai itself regardless of your
   own needs, and can be arbitrarily large or contain sensitive payload data; drop it explicitly at
   your own filtering boundary rather than relying on not looking at it.

**Also confirmed by reading the source** (worth checking before assuming it, since a leaked resource
is the kind of thing that's easy to assume without verifying): the `page.on("request"/"response"/
"requestfailed", ...)` listeners this feature attaches are explicitly removed in a `finally:` block
before the call returns, every time - no cross-call listener accumulation on a reused `session_id`,
even though the browser session/tab itself persists across calls.

## Some config flags that sound like real optimizations don't touch the phase their name implies - read the source before trusting the name

**Symptom observed**: asked to "optimize URL fetching," the obvious-looking crawl4ai levers
(`exclude_external_images=True` for bandwidth, `LinkPreviewConfig`'s `timeout` for a hung-request
guard) turned out, once actually read in source, to either do nothing for this specific
hook-driven/custom-JS crawler or to not even be the feature being reached for.

**Why it happens**: `exclude_external_images` (`content_scraping_strategy.py`) only strips `<img>`
tags from crawl4ai's own **post-fetch** content-scraping/markdown output - by the time that code
runs, the browser has already downloaded every image over the network, so it saves zero bandwidth.
Worse for a crawler shaped like this one: `PageState` here is built entirely from custom JS run via
hooks (`before_retrieve_html`/`on_execution_ended` - see this doc's own entries above), never from
crawl4ai's own extraction pipeline, so the flag is a complete no-op regardless of the bandwidth
question. `LinkPreviewConfig` (`CrawlerRunConfig.link_preview_config`) is a *different feature
entirely* - it configures crawl4ai's own link-preview/scoring pipeline (fetching each discovered
link's own content, concurrently, to score it), unrelated to this project's own link extraction
(`extract_links.js`). Never constructed/passed anywhere in this codebase, so tuning its `timeout`
touches nothing that runs.

**Fix pattern**: for real bandwidth savings, block the request at the network layer instead -
crawl4ai doesn't expose this as a config flag in this version, so it has to be a Playwright
`page.route()` handler, installed from the `on_page_context_created` hook:

```python
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}  # never "stylesheet"/"script"/"xhr"/"document"

async def _on_page_context_created(self, page, context, config, **kwargs):
    if self.block_images and not getattr(page, "_pragma_image_block_installed", False):
        await page.route("**/*", self._maybe_abort_media_request)
        page._pragma_image_block_installed = True  # this hook re-fires on every arun() for a
        # session, not just first page creation (confirmed in async_crawler_strategy.py) - without
        # this guard, a reused page accumulates a duplicate route() handler per interaction.
```

Two flags in the same investigation that *did* hold up under source-reading, for contrast - both
bound a real, different phase than this project's own `wait_seconds`/`interaction_wait_seconds`
(which only apply once a page has already loaded):
- `CrawlerRunConfig.page_timeout` (ms) bounds the raw `goto()`/`js_only` fetch itself - crawl4ai's
  own 60s default is real, wasted time on a genuinely hung request. Don't set this anywhere near
  `wait_seconds`'s own scale (a few seconds) though - too low reintroduces this doc's own
  `wait_for="css:body"`/pre-hydration-shell bug via a different code path (a slow-but-alive real SPA
  load killed before it ever finishes).
- `CrawlerRunConfig.prefetch=True` (confirmed in `async_webcrawler.py`) short-circuits crawl4ai's
  markdown-generation/content-scraping pipeline entirely - genuinely free for a crawler like this one
  (same reason `exclude_external_images` was a no-op: nothing here reads that pipeline's output)
  except one real side effect worth knowing before flipping it on: it also empties `result.markdown`,
  which is exactly what this project's own debug-log page-snapshot feature
  (`debug_logs/*/pages/*.md`, see
  [debugging-agent-systems.md](debugging-agent-systems.md)'s "read the raw debug log" discipline)
  reads. Shipped as an explicit off-by-default opt-in, not an unconditional flip, so an active
  debugging session doesn't silently lose that artifact.

**Update — a fourth phase found later, this time not a `CrawlerRunConfig` flag at all**: neither
`page_timeout` nor `wait_seconds`/`interaction_wait_seconds` bounds crawl4ai's *own internal* waits
inside a single interaction round-trip - e.g. `robust_execute_user_script` calling `page.wait_for_load_state
("domcontentloaded")` with **no explicit timeout of its own**, confirmed by reading crawl4ai's source
(this is the mechanism behind this doc's own "anti-bot heuristic can discard a signal already
captured" entry above: a session parked on a page whose `domcontentloaded` never fires - a WAF holding
the response open as an anti-automation measure - makes *every* subsequent interaction against that
session silently inherit Playwright's own hardcoded 30000ms default, one full 30s wait per attempt).
None of this project's own timeout knobs touch it, because it's Playwright's own *implicit* per-call
default, not anything `CrawlerRunConfig` exposes. `page.set_default_timeout()`, called once per
`arun()` in `on_page_context_created`, is what actually changes it - it only affects calls with no
explicit timeout of their own, so it's additive, not a conflict with `page_timeout`'s own already-
explicit value:

```python
async def _on_page_context_created(self, page, context, config, **kwargs):
    if self.interaction_timeout_seconds is not None:
        page.set_default_timeout(self.interaction_timeout_seconds * 1000)
```

Shrinks the cost of every wasted attempt against a dead/frozen session - complementary to, not a
substitute for, the circuit breaker above (which stops the *retrying*, not just the per-attempt cost).
