# `core/config.py`

## PragmaConfig

Wiring configuration for the Engine (which plugins, and crawl-tuning
settings).

`agents` holds optional per-provider settings (model, endpoint, etc.),
keyed by provider name, e.g. `{"local": {"model": "..."}}`. Secrets
should stay in env vars / `.env`; `agents` is meant for non-secret,
provider-specific overrides that would otherwise clutter a single flat
`.env` as more providers are added. Each provider is still free to fall
back to its own env vars when a key is omitted here - see the Config
dataclasses colocated with each Agent implementation.

## wait_seconds

Extra time to let a page settle before discovery reads it - carried over
from `PlaywrightScraper`'s own `wait_seconds`. Confirmed necessary
against a real JS-heavy SPA (empanad.app): the default `wait_for` alone
is satisfied by the pre-hydration HTML shell, so discovery can read 0
components/links on a page that has real ones once actually rendered.
Default is deliberately small; raise it for slow/JS-heavy sites.

## interaction_wait_seconds

Same purpose as `wait_seconds`, but applied after a click/fill's own
re-discovery instead of a full page's first load. `None` (default) falls
back to `wait_seconds` unchanged. Worth setting lower once a site's
confirmed to settle a same-page DOM update faster than its initial
hydration - measured live: every interaction pays this wait, so it's
usually the single largest fixed cost in a real crawl's wall-clock time
(a page with a few dozen components pays it a few dozen times).

## page_timeout_seconds

crawl4ai's own raw navigation/goto dead-page timeout (`page_timeout`,
converted to ms at the `Crawl4AICrawler` boundary) - NOT the same phase
as `wait_seconds`/`interaction_wait_seconds` above (those apply *after*
a page has already loaded; this bounds the underlying `goto()`/`js_only`
call itself). crawl4ai's own default is 60s - fine for correctness,
wasteful once a request is genuinely hung/dead. Keep this comfortably
above `wait_seconds`/`interaction_wait_seconds`'s own scale - setting it
too low reintroduces the pre-hydration-shell "0 components discovered"
bug via a different code path (a slow-but-alive real SPA load getting
killed before it ever finishes). See `Crawl4AICrawlerConfig`'s own
`page_timeout_seconds` entry.

## interaction_timeout_seconds

A THIRD timeout phase, distinct from both `page_timeout_seconds` above
and `wait_seconds`/`interaction_wait_seconds` - bounds Playwright's own
otherwise-unbounded-by-default internal waits inside one interaction
round-trip (e.g. crawl4ai's `robust_execute_user_script` calling
`page.wait_for_load_state("domcontentloaded")` with no explicit timeout
at all). `None` (default) leaves Playwright's own 30000ms default in
place. Confirmed live on austral.edu.ar: once a session lands on a page
whose `domcontentloaded` event never fires (a WAF holding the response
open as an anti-automation measure), every subsequent interaction
against that session silently ate a full 30s before failing - see
`Crawl4AICrawlerConfig`'s own `interaction_timeout_seconds` entry.

## prefetch

Skips crawl4ai's own markdown-generation/content-scraping pipeline
(crawl4ai's `prefetch` option) - real savings, since this project never
reads that pipeline's output (all facts come from this project's own
discovery JS instead). One real side effect: `data/debug_logs/*/pages/*.md`
snapshots (crawl4ai's markdown conversion of each page) come back empty
while this is on - leave `False` during an active debugging session that
still wants to read those; `True` for a bulk/production run. See
`Crawl4AICrawlerConfig`'s own `prefetch` entry.

## block_images

Aborts image/media/font network requests outright via a Playwright
`page.route()` handler - real bandwidth/load-time savings, unlike
crawl4ai's own `exclude_external_images` (which only strips
already-downloaded images from crawl4ai's own output; see
`Crawl4AICrawlerConfig`'s `block_images` entry for why that flag does
nothing for this project). A real behavior change (a site whose
interactive elements depend on images actually loading could behave
differently) - off by default, opt in per-site once confirmed safe.

## element_budget

Per-page cap on how many components `MechanicalCrawler` mechanically
interacts with in a single visit-pass - the backstop against a
pathological reveal-chain, not a normal-case limiter (default generous
enough that ordinary pages never hit it). See
`docs/dev/spiders/orchestration/mechanical_loop/loop.md#module`.

## max_pages

Total pages `MechanicalCrawler.crawl_site` will visit before stopping,
`None` = unbounded (crawl until the URL frontier is exhausted). A page
re-queued after a navigation-interrupted pass (see
`docs/dev/spiders/orchestration/visit_result.md#pagevisitresultinterrupted_by_navigation`)
counts as its own visit here.

## max_passes_per_page

Max times `MechanicalCrawler` will revisit the same page to keep
draining its interaction frontier (a page whose components exceed
`element_budget` needs more than one pass) before giving up on it
gracefully. Backstop against a page that keeps generating genuinely new
content faster than one pass's budget can keep up with
(infinite-scroll/live-chat-style) - same "backstop against a
pathological case" philosophy as `element_budget` itself.

## prd_synth_batch_size

Max pages' worth of section content `GraphPRDSynthesizer.synthesize`
batches into a single "batch summarize" `agent.generate()` call before a
final, much smaller "reduce" call combines the per-batch summaries - the
fix for a single unbounded synthesis prompt hitting a local model's
`max_tokens` truncation on real sites (confirmed live on empanad.app,
4/4 runs: see docs/explicativos/avance-corridas-gemma-empanadapp.md).
Kept small deliberately - each page's block already includes a full
narrated component catalog, not just a short label, so this is a
heavier per-item budget than `element_budget`/`max_passes_per_page`
above.

## max_visits_per_route_shape

Backstop against a site that mints a fresh, per-visit-token URL (e.g. a
`/o/<random-hash>` order flow) on essentially every top-level visit -
confirmed live on empanad.app: each token is a distinct real identity
(`clean_url()` correctly keeps them apart), so an unbounded frontier
would treat every new token as a brand-new page forever and never
converge, burning a full interaction pass on what's structurally the
same page every time. `route_shape()` (`utils/urls.py`) collapses
same-shaped URLs for this bounding check only - real navigation/identity
is untouched. Default 1: an ordinary site has no repeated route shapes
at all, so this never fires; raise it to deliberately sample more than
one instance of a session-token route. See
`MechanicalCrawlerConfig.max_visits_per_route_shape`.

## ai_fill_values

Whether `MechanicalCrawler` asks `agent` to generate a realistic fill
value for each fillable field (a real network+generation round trip per
field - can dominate wall-clock time against a slow/remote model).
`False` falls back to the fast, deterministic placeholder instead - set
this off for a speed-focused run that doesn't need realistic fill values
in the output.

## page_concurrency

How many pages `MechanicalCrawler.crawl_site` visits concurrently.
Default 1 keeps the original fully-sequential crawl (every earlier
behavior/guarantee holds exactly as before) - raise it to actually cut
wall-clock time on a large site: fixed per-interaction waits
(`wait_seconds`/`interaction_wait_seconds`) are what make a sequential
crawl slow in practice, and they overlap across concurrently-visited
pages instead of serializing. See `MechanicalCrawler`'s own docstring
for what this changes under the hood and its tradeoffs (a soft, not
hard, bound on `max_pages` once concurrency > 1).

## allow_subdomains

Whether same-site scoping (which links `MechanicalCrawler`'s URL
frontier will actually visit - see `utils/urls.py`'s
`is_in_scope()`, the single choke point in `MechanicalCrawler._enqueue()`)
treats a subdomain (e.g. `blog.example.com`) as in-scope for a crawl of
`example.com`. A link (or a click/redirect landing) on any *other* host
is always out of scope, regardless of this setting - the
interaction/edge that led there is still recorded, it's just never
itself crawled further. Off by default: exact host match only. A naive
last-two-label heuristic when enabled, not a full public-suffix-list
lookup.

## fresh

Purge this site's previously recorded `graph_store` state before
crawling (`Engine.from_config`). Matters for `graph_store: neo4j`, which
persists across runs - without this, a site whose URLs are per-session
tokens (e.g. a `/o/<random-id>` order flow) accumulates a "visited" node
per past run forever, none of which will ever be seen again but all of
which the synthesis step still reads back as history. `graph_store:
memory` never persists across runs regardless, so this is a no-op there
either way. Set to `false` to resume a previous run's progress on a
genuinely multi-session crawl of a large, stable site.

## debug_logs_dir

Where per-run debug artifacts go: `data/debug_logs/{slug}_{timestamp}/debug.md`
(every crawl4ai hook firing, appended live) and `.../pages/{page}.md`
(crawl4ai's own markdown conversion of each page, last-seen snapshot).
Set to `""` (empty string) to disable debug logging entirely - see
`spiders/browser/debug_log.py` and `Engine._run_async`.

## debug_logs_keep_last

Max number of past `debug_logs_dir` run directories to keep for this
same site+URL (see `spiders/browser/debug_log.py::prune_old_runs`), oldest
deleted first. `None` (default) keeps every run forever, unchanged from
before this setting existed - opt in once unbounded `data/debug_logs/` growth
becomes a real disk-space concern for a site crawled repeatedly. A
no-op whenever `debug_logs_dir` is disabled (there's nothing to prune).

## export_json

Also write `data/output/{slug}_graph_{timestamp}.json` - the full crawl graph
(pages, edges, component ledger, text content) as structured JSON,
alongside the prose PRD and the ASCII component tree - for a downstream
tool that wants to consume the crawl's facts as data instead of
documents meant for a person to read. Off by default so existing
`out_dir` layouts don't suddenly grow an extra file per run without
opting in. See `generators/graph_export.py`.

## tree_ascii

Component-tree document (`data/output/{slug}_tree_{timestamp}.md`) rendering
mode - Unicode box-drawing characters (`tree` command style) by default;
`True` falls back to plain ASCII for terminals/environments that mangle
Unicode. See `generators/component_tree.py::render_ascii_tree`.

## load

Build a `PragmaConfig` by merging env vars, an optional YAML file, and
CLI flags.

Precedence (highest wins): explicit CLI flag > YAML file value > env var
> default.

## documents

Which output documents a run generates, by `DOCUMENT_REGISTRY` name, in
order. Defaults to `["coverage", "prd", "tree"]` - coverage first because
it is the cheapest and the one that frames the other two.

The master document ("Start Here") is deliberately absent from this list:
it is the pipeline's closing step rather than an optional document, and
listing it would let it be scheduled in the middle, where it would index
only whatever ran before it. See
`docs/dev/generators/master_document.md#masterdocument`.

`export_json` stays a separate boolean rather than being folded in here,
so an existing `pragma.yaml` that sets it keeps working unchanged -
`Engine._document_names` appends `"export"` when the flag is on and the
list did not already ask for it. Setting both is not an error; the name is
added once.
