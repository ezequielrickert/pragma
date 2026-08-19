# spiders/browser/login_session.py

## module

Login-session file management and the headed capture flow itself.
Deliberately has no opinion on *when* a session should be captured (see
`spiders/browser/login.py` for that orchestration) - this module only
answers "where does site X's session live", "is the file at this path
still good", "does this page even need one", and "go capture one".

## _LOGIN_TRIGGER_KEYWORDS

Case-insensitive substrings that mark a button/link as a login trigger -
English and Spanish (the project's other real target sites are
Spanish-language), covering the common phrasings without trying to be
exhaustive.

## session_path

Where `site`'s captured storage_state lives, whether or not it exists
yet - `<sessions_dir>/<site>.json`.

## is_session_valid

True when `path` exists and is younger than `max_age_hours`. A missing
or stale session must never be handed to the real crawl as if it were
still good - an expired cookie fails the crawl silently (pages just
render logged-out) rather than raising, so staleness has to be caught
here, before that crawl ever starts.

## has_login_form

True when any discovered component is a password input - the one
reliable signal across arbitrary sites present in the page as first
loaded. Label text, form action, and button copy vary too much to
pattern-match, but a `<input type="password">` means a login gate
regardless of how the surrounding page phrases it. Misses a form that
only mounts after a click - see `find_login_trigger` for that case.

## find_login_trigger

CSS path of a button/link whose visible text reads like a login trigger
(e.g. "Iniciar Sesión", "Log in"), or `None`. `has_login_form` alone
misses a real, common case: a site (e.g. a React/Vue SPA) that mounts
its password field only after this kind of element is clicked - a
modal, an inline form swap - so nothing resembling a login form exists
in the page as first loaded. This is the one extra hop
`ensure_login_session` takes before concluding a page has no login gate
at all.

## capture_login_session

Opens a real, headed browser at `url`, lets a human sign in by hand,
then persists the resulting cookies/localStorage to `save_path`. Blocks
on stdin via `asyncio.to_thread` rather than a bare `input()` call, so
this coroutine's event loop keeps servicing the browser (and anything
else running alongside it) while a human is off in a separate window
typing a password.
