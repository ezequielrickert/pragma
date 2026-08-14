# `spiders/debug_log.py`

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
- `pages/{page-slug}.history.md` - crawl4ai's own readable-markdown
  conversion of each page, every snapshot ever saved for that session/page,
  in order, each under its own timestamped heading, never overwritten - so
  the actual textual content driving the crawl is directly inspectable
  without re-running anything, and an earlier, more-interesting snapshot
  (e.g. a component's revealed items) survives even if a *later* call in
  the same session would otherwise have overwritten it.

**Added after a real symptom on austral.edu.ar**: a single page visit calls
`save_page_markdown` once per interaction within that session (every
`discover_page`/`_interact`/`resync` call - see `Crawl4AICrawler._save_markdown`),
not just once per page. An earlier live-snapshot design (one file per page,
overwritten on every call) silently lost the earlier, more-interesting
snapshot the moment a later interaction changed the DOM again - this is
exactly wiki/graph-based-crawl-tracking.md's "separate the live snapshot
from the append-only audit trail" principle: only an append-only history
can answer "what did this page look like at the moment component X's items
were discovered." The overwrite-only live file was dropped entirely (see
`save_page_markdown` below) once nothing in the extraction pipeline was
found to read it - it was pure debug convenience, fully subsumed by the
history file's last entry.

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
scheme-strip discipline as `clean_url` (`utils/urls.py`), plus
replacing path separators, since a URL is not a valid filename as-is.

## CrawlDebugLog

Owns both debug artifacts for one crawl run.

**Writes are queued, not inline.** Every public method (`log_hook`,
`log_event`, `save_page_markdown`) builds a job and returns immediately;
a single background task (`_drain`, started lazily on first use by
`_ensure_writer`) pulls jobs off `self._queue` in FIFO order and runs each
one via `asyncio.to_thread`, so the actual `open`/`write`/`flush` work
never blocks the coroutine that's mid-navigation or mid-extraction in
`Crawl4AICrawler`. One writer task processing the queue serially is what
keeps `debug.md` and `pages/*.history.md` in the same chronological order
they were enqueued in, and is also what makes concurrent `PageVisitor`
workers safe to call into without interleaving mid-write - see
`MechanicalCrawler._in_flight` (`mechanical_loop.py`) for the unrelated,
already-fixed race this class used to be exposed to before `session_id`
keying (kept as history, not current risk).

## _ensure_writer

Starts `_drain` as a background task on first enqueue, not in `__init__` -
`asyncio.create_task` needs a running event loop, and `CrawlDebugLog` is
constructed before one is guaranteed to exist at every call site (e.g. a
future sync test harness). Every current production call site only
enqueues from inside `Crawl4AICrawler`'s async hook machinery, which never
runs without a live loop, so this is a formality that also keeps the
constructor itself loop-agnostic.

## _drain

Runs forever, pulling one job at a time off `self._queue` and executing it
via `asyncio.to_thread` so its blocking file I/O doesn't stall the event
loop. Processing strictly one job at a time (not fanned out) is what
preserves enqueue order across `debug.md` and the history files, and
avoids two writer threads racing on the same open file handle. Stopped by
`close()` cancelling this task after everything already queued has
drained.

## log_hook_from_raw

`log_hook`, but for a crawl4ai hook callback registered purely for its
debug-log side effect (`Crawl4AICrawler._log_only_hook`) - extracts the
loggable facts from the hook's raw call signature via
`loggable_hook_details` first, since those callbacks have nothing more
specific of their own to pass in.

## log_hook

Queue one entry for a single hook firing. `details` is rendered as a
flat bullet list, in insertion order - callers pass whatever's
relevant/available for that specific hook (see `Crawl4AICrawler`'s
per-hook logging calls), not a fixed schema every hook must fill in.

## log_event

Queue a free-text entry not tied to a specific crawl4ai hook - e.g. a
page-visit summary from `MechanicalCrawler` itself, so the log reads as
one continuous timeline rather than only ever showing raw hook noise with
no higher-level narrative. Currently unused anywhere in this project - kept
for parity with `log_hook`, not because anything calls it today.

## save_page_markdown

Queue crawl4ai's own markdown conversion of `url`'s current content onto
`pages/{slug}.history.md` (see this doc's `module` section for why only
the history file exists). Also queues a `page_markdown_saved` entry in
`debug.md`, as part of the same job, so the two stay in relative order
without a second round trip through the queue. Returns the history file's
path immediately - it's a deterministic string join, no I/O required to
compute it, so callers don't have to wait on the queued write to get it.

## close

Drain every job already queued (`await self._queue.join()`), cancel the
background writer task, then close the file handle. Awaiting `join()`
before cancelling is what guarantees every write requested before `close()`
was called actually lands on disk - cancelling first could drop whatever
was still in flight. `Engine._run_async` awaits this before calling
`prune_old_runs`, same ordering requirement as before this class's writes
became queued.

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
`await CrawlDebugLog.close()` - pruning mid-run would risk deleting the
very directory the current run is still writing into if `keep_last` were
ever set to something small enough to include it.
