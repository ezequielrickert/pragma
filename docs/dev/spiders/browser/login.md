# spiders/browser/login.py

## module

Login orchestration - the decision of *when* to capture a session,
decoupled from any one caller. `ensure_login_session` is the auto-invoke
hook contract a crawl stage (`pragma static`, `pragma dynamic`) calls
before it opens its own real browser, instead of crashing on a login
wall or re-deriving this same reuse-cache/precheck/capture decision
itself. Depends only on `Crawl4AICrawler` for the precheck navigation,
never on `Engine` or any other orchestrator - the coupling that made the
previous login attempt (discarded, never committed) hard to reuse from
more than one call site.

## ensure_login_session

Storage-state path a real crawl of `url` should launch with, or `None`
for an anonymous crawl. A valid cached session is used directly. Otherwise
a throwaway `Crawl4AICrawler` (governed by this function's own `headless`
argument - a background, non-interactive DOM check, nobody needs to see
it) visits `url` once to check for a login form.

Many sites (React/Vue SPAs especially) mount their password field only
after a "Log in"/"Iniciar Sesión"-style button is clicked - nothing
resembling a form exists on the page as first loaded - so a page with no
login form yet gets one more chance: `find_login_trigger` spots such a
button/link, the precheck clicks it, and checks again. Either a
confirmed login form or a merely-plausible trigger opens the real,
always-visible capture browser (`capture_login_session`, unconditionally
`headless=False` regardless of this function's own `headless` argument -
a headless window is useless to the human who has to actually click
through it): a confirmed form is signed into directly; a trigger that
led nowhere automatically still gets opened, on the working assumption
that a human looking at the real page can finish a multi-step flow (an
OAuth/email choice screen, a second click) this precheck was never meant
to chase on its own - confirmed live against a real site whose login
needed two clicks plus a Google/Email choice. A page with no login form
and no trigger at all costs nothing beyond that one precheck visit.

## _click_login_trigger_if_any

One extra click, if the current `PageState` has a plausible login
trigger and nothing resembling a login form yet. Returns
`(post_click_page_state, True)` when a trigger was clicked, or
`(page_state, False)` unchanged when there was nothing to click - the
caller uses that flag to tell "no login gate at all" apart from "found
one, couldn't finish it automatically". A click that fails outright (the
element vanished, an unrelated error) is treated the same as "no trigger
found" - this is a best-effort second look, not something the caller
should ever crash over.

## force_login_session

Always captures a fresh session, regardless of a still-valid cached one
- the standalone `pragma login` command's entry point. A human running
that command by hand is explicitly asking to sign in, so it skips both
the reuse check and the login-form precheck `ensure_login_session` uses
to stay quiet on pages that don't need it, and - like every capture -
always opens a real, visible browser: there is no such thing as a
headless interactive sign-in.
