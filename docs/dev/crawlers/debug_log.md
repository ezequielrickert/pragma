# `src/crawlers/debug_log.py`

## module

Two artifacts per crawl run, both under one timestamped directory
(`debug_logs/{slug}_{timestamp}/` by default - see `PragmaConfig.debug_logs_dir`
and `Engine._run_async`):

- `debug.md` - an append-only, human-readable record of every crawl4ai hook
  firing during the run (which hook, when, on what URL/session, with what
  result) - the append-only "audit trail" half of
  wiki/graph-based-crawl-tracking.md's "separate the live snapshot from the
  append-only audit trail" principle, applied to hook events instead of a
  research log. This is what to open when a crawl behaved unexpectedly and
  `GraphStore`'s final state alone doesn't explain *how* it got there.
- `pages/{page-slug}.md` - crawl4ai's own readable-markdown conversion of each
  page *as most recently seen* (overwritten on every save for that
  session/page - a live snapshot, for "what does this page look like right
  now" at a glance), so the actual textual content driving the crawl is
  directly inspectable without re-running anything.
- `pages/{page-slug}.history.md` - the append-only companion to the file
  above: every snapshot ever saved for that session/page, in order, each
  under its own timestamped heading, never overwritten.

**Added after a real symptom on austral.edu.ar**: a single page visit calls
`save_page_markdown` once per interaction within that session (every
`discover_page`/`_interact`/`resync` call - see `Crawl4AICrawler._save_markdown`),
not just once per page. When one interaction reveals rich content (e.g. a
component with a list of items) and a *later* interaction in the same pass
changes the DOM again (even an unrelated one elsewhere on the page), the
live `.md` file above - being overwrite-only - silently loses the earlier,
more-interesting snapshot with no trace it ever existed. This is exactly
wiki/graph-based-crawl-tracking.md's "separate the live snapshot from the
append-only audit trail" principle, applied here: the live file alone
cannot answer "what did this page look like at the moment component X's
items were discovered," only the history file can.

## loggable_hook_details

Pull the small, markdown-friendly facts out of a crawl4ai hook call's raw
args/kwargs, for `CrawlDebugLog.log_hook_from_raw` - a target `url`, a
response `status`, a new `user_agent`, captured `html`'s length - falling
back to the live `page.url` when a hook carries no more specific fact of
its own. Every hook (per crawl4ai's own `set_hook` docstring) is called
with `page`/`context` plus hook-specific kwargs, except `on_browser_created`
(`browser`, `context`) - none of that is JSON/markdown-friendly on its
own, so only these specific facts get pulled out.

## _page_slug

Filesystem-safe filename for one page's markdown snapshot - same
scheme-strip discipline as `clean_url` (`src/utils/urls.py`), plus
replacing path separators, since a URL is not a valid filename as-is.

## CrawlDebugLog

Owns both debug artifacts for one crawl run.

**Update — this class predates `page_concurrency` (`MechanicalCrawler` can
now run several `PageVisitor.visit()` coroutines at once) and the note that
used to stand here ("a single crawl is driven by one sequential coroutine,
no concurrent `arun()` calls") is no longer true - kept only as history for
why the plain-buffered-file-handle design below is still fine despite
that:** every `log_hook`/`log_event`/`save_page_markdown` call here is a
single synchronous method with no `await` inside it, so asyncio's
cooperative scheduling (never preempts mid-call, only at an `await` point)
makes each individual call atomic - concurrent workers' calls interleave
in time, appending whole entries in whatever order they actually complete,
never mid-write. `debug.md`'s append-only shape is genuinely safe under
concurrency for exactly this reason.

`pages/{slug}.md` was a real exception, since it isn't append-only:
confirmed live on a real crawl (mapadeprofesionales.com,
`page_concurrency=10`) that many distinct pages redirecting to the same
destination could, before `Crawl4AICrawler._save_markdown` started keying
by `session_id` instead of the post-redirect URL, overwrite one another's
snapshot - a real information loss, not just interleaved output. See
`MechanicalCrawler._in_flight` (`mechanical_loop.py`) for the deeper fix
of the underlying race this symptom came from.

## log_hook_from_raw

`log_hook`, but for a crawl4ai hook callback registered purely for its
debug-log side effect (`Crawl4AICrawler._log_only_hook`) - extracts the
loggable facts from the hook's raw call signature via
`loggable_hook_details` first, since those callbacks have nothing more
specific of their own to pass in.

## log_hook

Append one entry for a single hook firing. `details` is rendered as a
flat bullet list, in insertion order - callers pass whatever's
relevant/available for that specific hook (see `Crawl4AICrawler`'s
per-hook logging calls), not a fixed schema every hook must fill in.

## log_event

Append a free-text entry not tied to a specific crawl4ai hook - e.g. a
page-visit summary from `MechanicalCrawler` itself, so the log reads as
one continuous timeline rather than only ever showing raw hook noise with
no higher-level narrative.

## save_page_markdown

Save crawl4ai's own markdown conversion of `url`'s current content.

Writes two files (see this doc's `module` section for the full rationale):
- `pages/{slug}.md` - overwritten every call, the current-content
  convenience snapshot.
- `pages/{slug}.history.md` - appended every call, never overwritten, so a
  snapshot that showed real discovered content (e.g. a component's
  revealed items) survives even if a *later* call in the same session
  overwrites the live file with different content - this is the file to
  open when the live snapshot doesn't show something you saw earlier in a
  real crawl run.

Logs a reference to both in `debug.md`. Returns the live file's path
(unchanged return contract from before the history file was added).

## prune_old_runs

Delete this site's oldest `debug_logs/{slug}_{timestamp}/` run directories
beyond `keep_last`, keeping the most recent ones. `None` or a
non-positive `keep_last` is a no-op (returns `[]`) - unbounded retention
is the existing, unchanged default; this is opt-in.

Scoped to `slug` (not a global cap across every site this project has
ever crawled) by only matching directories named `{slug}_<timestamp>` -
crawling one site a lot must never evict another site's debug history
just because it happened to run more recently. `_timestamp()`'s format
(`%Y%m%dT%H%M%SZ`) sorts correctly as a plain string, so directory name
order is chronological order - no need to parse it into a real datetime
just to decide which ones are oldest.

Called once a run finishes (see `Engine._run_async`), after
`CrawlDebugLog.close()` - pruning mid-run would risk deleting the very
directory the current run is still writing into if `keep_last` were ever
set to something small enough to include it.
