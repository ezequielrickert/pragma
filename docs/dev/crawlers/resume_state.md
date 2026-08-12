# `src/crawlers/resume_state.py`

## module

Rebuilds a crawl's URL frontier from what a previous session already
recorded in the graph store.

There is no checkpoint file, and deliberately so. Everything a resume
needs was already being written during the crawl, one page at a time:

- `GraphStoreSink.record_page_arrival` upserts a page as `Pending` before
  discovery touches it.
- `GraphStoreSink.record_page_finished` flips it to `Finished`, and only
  when the pass completed without being cut short (`page_visitor.md`).
- `record_links` / `record_edge` MERGE every discovered destination as a
  `Pending` page of its own, so a URL that was queued but never reached is
  in the store too.

So "unfinished work" is already a query, not a thing to persist: any page
that is not `Finished`. A page abandoned mid-pass — by a stop, a crash, a
Ctrl-C — never reached `record_page_finished` and is therefore
indistinguishable from one never visited, which is exactly right. Both
need another pass, and neither needs bookkeeping beyond what the crawl
was writing anyway.

crawl4ai's own checkpointing was evaluated and does not apply: its
`resume_state`/`on_state_change`/`should_cancel` triad lives on the deep-
crawl strategies, and `CrawlState.save/load` on `AdaptiveCrawler`. Both
are reached only by handing crawl4ai the crawl loop, and Pragma drives
`arun()` per URL with its own frontier (see `crawl4ai_crawler.md`).

## _finished_status

The one `GraphStore` page status that means "no further work". Named
rather than inlined because the negative case is the interesting one —
everything else is frontier work — and a silent typo here would resume a
crawl that re-visits every page it already finished.

## resumeplan

What a previous session's rows say about where its frontier stood.
Purely descriptive; applying it is `mechanical_loop.md#resume`'s job.
Keeping the read and the apply apart is what lets the whole rehydration
be tested against literal dictionaries, with no store and no crawler.

### route_shape_visits

`route_shape()` key → how many pages of that shape already finished.

Without this, `max_visits_per_route_shape` would restart from zero on
every resume, and the bound it exists to enforce would never actually
hold across sessions — a site minting a fresh per-visit token URL (the
empanad.app `/o/<hash>` case that motivated the knob) would get one more
sampled instance per resume, forever.

### is_empty

Whether there is nothing to resume: no prior session at all, or one whose
rows carry neither pending nor finished pages. `finished_count` alone
keeps this false — those pages still have to be skipped rather than
recrawled, so the plan is worth applying even with an empty pending list.

## restore_frontier

Turns one site's `GraphStore.get_progress_table_rows` output into a
crawlable frontier.

`get_progress_table_rows` rather than `get_pending`, even though the
latter exists and returns precisely the pending URLs: the finished rows
are needed too, for `route_shape_visits` and for `finished_count`. One
read of everything beats two reads that have to agree with each other.

**The scheme is load-bearing.** Graph keys are `clean_url()` output
(`utils/urls.md#clean_url`), which strips the scheme and any leading
`www.` — that is what makes them stable dedup keys, and what makes them
un-navigable. `a.com/pricing` is not a URL. The scheme is taken from the
run's own start URL rather than assumed, since the crawl fixtures and any
local target run on `http`. A stripped `www.` costs at most one redirect,
which the crawler's `resolved_url` handling already absorbs.

Scope is *not* filtered here. `record_links` records off-site link
targets as `Pending` pages too, so a raw pending list contains URLs this
crawl must never visit. Filtering them here would duplicate the scope
rule that `MechanicalCrawler._enqueue` already owns, and duplicate it
somewhere with no access to `base_url`/`allow_subdomains` — so
`resume` feeds every URL through `_enqueue` instead, and the existing
gate rejects them exactly as it would mid-crawl.
