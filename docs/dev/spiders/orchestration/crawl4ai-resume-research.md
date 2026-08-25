# crawl4ai native resume_from / state-callback contract: BestFirstCrawlingStrategy

Research for issue [#249](https://github.com/ezequielrickert/pragma/issues/249) (`CrawlEngineCore`
rewire onto native `arun`+stream), part of map [#245](https://github.com/ezequielrickert/pragma/issues/245).
Findings only — no implementation. Investigated against the actually-installed
`crawl4ai==0.9.2` source in this repo's `.venv`
(`.venv/lib/python3.11/site-packages/crawl4ai/`), confirmed via
`python -c "import crawl4ai; print(crawl4ai.__file__)"` →
`/Users/ezequielrickert/projects/pragma/.venv/lib/python3.11/site-packages/crawl4ai/__init__.py`.

## Question 1 — resume_from / `_resume_state` shape for `BestFirstCrawlingStrategy`

`BestFirstCrawlingStrategy.__init__` (`bff_strategy.py:36-73`) accepts `resume_state:
Optional[Dict[str, Any]]` (no separate `resume_from` parameter — the constructor kwarg itself
*is* the resume mechanism), stored unchanged as `self._resume_state` (`bff_strategy.py:68`).

Consumed only inside `_arun_best_first` (`bff_strategy.py:210-233`), guarded by `if
self._resume_state:`. The expected keys:

| key | type | meaning | source line |
|---|---|---|---|
| `visited` | iterable of `str` | seeds `visited: Set[str]` | `bff_strategy.py:212` |
| `depths` | `dict[str, int]` | seeds `depths: Dict[str, int]` | `bff_strategy.py:213` |
| `pages_crawled` | `int` (default `0`) | seeds `self._pages_crawled` | `bff_strategy.py:214` |
| `queue_items` | `list[dict]`, each `{"score": float, "depth": int, "url": str, "parent_url": Optional[str]}` | rehydrates the `asyncio.PriorityQueue` one item at a time via `queue.put((item["score"], item["depth"], item["url"], item["parent_url"]))` | `bff_strategy.py:216-218` |

If `_on_state_change` is also set, a parallel `_queue_shadow: List[Tuple[score, depth, url,
parent_url]]` is rebuilt from the same `queue_items` (`bff_strategy.py:220-224`) — it exists
only because `asyncio.PriorityQueue` can't be iterated/snapshotted for the callback, so the
strategy keeps a plain-list mirror in lockstep with every `put`/`get`.

**Contrast with `BFSDeepCrawlStrategy` (`bfs_strategy.py`):** confirmed via grep
(`bfs_strategy.py:221-228` and the mirrored `:317-324` block in the other of its two internal
run methods) that BFS's `_resume_state` uses a **`pending`** key (list of `(url, parent_url,
depth)`-shaped tuples reconstructed into its level-by-level frontier), not `queue_items` — no
`score` field at all, since BFS has no priority queue. This confirms the ticket's warning:
**the two strategies do not share resume-state shape.** BestFirst's frontier is inherently a
priority queue, so its serialized state carries a `score` per pending item that BFS's shape has
no equivalent for; a translation layer cannot naively rename `pending` → `queue_items` — it must
also invent a `score` for every URL being seeded back in (see Q4).

## Question 2 — `_on_state_change` call contract for `_arun_best_first`

Signature: `on_state_change: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]`
(`bff_strategy.py:47`) — an async callback taking one dict, no return value used.

**When it fires:** per-URL, immediately after that URL's own successful link discovery
completes, still inside the per-batch `for score, depth, url, parent_url in batch:` loop
(`bff_strategy.py:286-345`). Concretely: after `link_discovery` runs and every newly-discovered
link has been scored and pushed onto both the real queue and `_queue_shadow`
(`bff_strategy.py:312-329`), the state dict is built and awaited at `bff_strategy.py:331-345`.
It is **not** per-dequeue (dequeuing at `bff_strategy.py:259` does not itself trigger a
callback — only removes the item from `_queue_shadow`), and **not** per-level (there is no
level concept in best-first — items are pulled in `BATCH_SIZE`=10 batches
(`bff_strategy.py:19,248,256-273`) purely for `arun_many` fetch efficiency, but the callback
still fires once per successfully-processed URL within that batch, not once per batch). A
failed-crawl result (`result.success` False) skips both link discovery and the callback
entirely (`bff_strategy.py:296,310`) — the callback only fires after successful pages.

One extra unconditional call happens outside the loop: if the crawl was cancelled
(`self._cancel_event.is_set()`), a final state snapshot is pushed once more after the `while`
loop exits (`bff_strategy.py:348-361`), with `"cancelled": True`.

The dict shape passed to the callback (identical in the per-URL and final-cancellation calls):

```python
{
    "strategy_type": "best_first",
    "visited": list(visited),
    "queue_items": [{"score": s, "depth": d, "url": u, "parent_url": p} for s, d, u, p in self._queue_shadow],
    "depths": depths,
    "pages_crawled": self._pages_crawled,
    "cancelled": self._cancel_event.is_set(),  # or hardcoded True in the final call
}
```
(`bff_strategy.py:333-343`, `:350-359`). This is exactly the shape `resume_state` expects back
on construction — round-trippable by design. Each call also assigns the same dict to
`self._last_state` (`bff_strategy.py:344`, `:360`), which is what the public
`export_state()` method returns (`bff_strategy.py:419-429`) — `export_state()` is a
point-in-time read of the *last* callback payload, not a live/independent snapshot.

## Question 3 — which class/file owns this logic

All of it lives in `BestFirstCrawlingStrategy` itself, in
`.venv/lib/python3.11/site-packages/crawl4ai/deep_crawling/bff_strategy.py` — there is no
shared/base module involvement:

- Constructor + field storage: `bff_strategy.py:36-73`
- Resume-state consumption: `bff_strategy.py:210-233`
- State-change emission: `bff_strategy.py:331-345` (per-URL), `:348-361` (final/cancelled)
- `export_state()`: `bff_strategy.py:419-429`

The abstract base it extends, `DeepCrawlStrategy` in
`.venv/lib/python3.11/site-packages/crawl4ai/deep_crawling/base_strategy.py:45-159`, declares
only the shape-agnostic contract (`_arun_batch`, `_arun_stream`, `arun`, `shutdown`,
`can_process_url`, `link_discovery`) — it has **no** `resume_state`, `on_state_change`,
`_resume_state`, or `export_state` members at all (confirmed by reading the full file: no such
identifiers appear anywhere in `base_strategy.py`). Every resume/state-callback name is grepped
as present only in `bff_strategy.py` and, separately and differently-shaped, in `bfs_strategy.py`
— each strategy subclass owns its own copy of this plumbing independently, matching the
ticket's warning and this project's own `deep_crawl_strategy.py:27-29` docstring note that
`BFSDeepCrawlStrategy` and `BestFirstCrawlingStrategy` "don't share a common ancestor below"
`DeepCrawlStrategy`.

## Question 4 — mapping pragma's `GraphStore.get_pending()`/`get_scouted()` onto this shape

Read: `spiders/orchestration/engine_core.py:143-169` and
`database/ladybug/page.py:172-198` (the `LadybugGraphStore` mixin these calls hit, composed
into the public class at `database/ladybug/store.py:150`).

`CrawlEngineCore._resume_urls()` (`engine_core.py:143-156`) calls
`self.sink.graph_store.get_pending()`, which runs `MATCH (p:Page) WHERE p.status = 'Pending'
RETURN p.url ORDER BY p.url` (`database/ladybug/page.py:172-183`) — a **flat, ordered
`List[str]`** of URLs, nothing else. `_scouted_urls()` (`engine_core.py:158-169`) is the same
shape from `get_scouted()` (`database/ladybug/page.py:185-198`), just filtered to
`status = 'Scouted'`. Neither query result carries a score, a depth, a parent URL, or a
"pages already crawled" count — none of the fields `BestFirstCrawlingStrategy._resume_state`
expects beyond the bare URL list.

Translation needed to seed a resumed best-first crawl from this read-back:

1. **`visited`** — not directly available from either query as written. `get_pending()` /
   `get_scouted()` only return *unfinished* work; pragma's graph also holds `Finished` and
   `Failed` pages (`page.py:161-168`'s `is_visited` checks exactly those two statuses). A
   correct `visited` set for resume needs every page whose status is `Finished`, `Failed`, or
   `Scouted` (i.e. already dequeued/processed at least once) — `get_progress_table_rows()`
   (`page.py:200-212`) already returns `{"url", "status", "components"}` for every page and
   would need to be filtered pragma-side rather than reusing a single existing getter.
2. **`depths`** — GraphStore's `Page` nodes carry no depth property in any of the query
   projections read here (`get_pending`, `get_scouted`, `get_progress_table_rows` all project
   only `url`/`status`/`component_count`). Depth information is not queried back at all today;
   either it must be added as a stored `Page` property and threaded through `upsert_page`
   (`page.py:38-75`), or reconstructed from `PragmaDeepCrawlStrategy`'s own frontier-shape
   tracking if that data survives a process restart (it does not — it's in-memory state on the
   strategy object, not persisted to the graph).
3. **`queue_items` (score/depth/url/parent_url tuples)** — the biggest gap. `get_pending()`
   returns bare URLs with no ordering signal beyond alphabetical `ORDER BY p.url`
   (`page.py:178`) and no `parent_url` (pragma's graph models parent/child via
   `NAVIGATES_TO` edges, not a `Page` property — see the edge-write query at
   `page.py:144-157` in the surrounding file, distinct from `get_pending`). To seed
   `BestFirstCrawlingStrategy`'s priority queue, pragma would need to: (a) look up each
   pending URL's inbound `NAVIGATES_TO` edge to recover a `parent_url` (or accept `None`,
   which the shape permits), (b) recompute a `score` for each URL via
   `PragmaBestFirstStrategy`'s own `url_scorer.score(url)` at resume time (the scorer is
   deterministic and stateless per `docs/dev/spiders/orchestration/route_shape_scorer.md`, so
   this is a re-derivation, not a stored value — no score is persisted in the graph today), and
   (c) supply a `depth` per URL, which per point 2 has no current storage path.
4. **`pages_crawled`** — recoverable as `count(status IN ('Finished','Failed'))` — close to
   what `get_progress_table_rows()` already aggregates for the dashboard's finished/total pair
   (`page.py:200-212`, and the separate finished/total count query at `page.py:243-244`), just
   not currently exposed as a single int getter.

**Net finding:** `get_pending()`/`get_scouted()` as they exist today answer "which URLs are
outstanding," which is necessary but not sufficient for `BestFirstCrawlingStrategy.resume_state`
— that shape additionally demands per-URL `score`, `depth`, and `parent_url`, plus a `visited`
set spanning more statuses than either getter alone returns. None of `score`, `depth`, or
`parent_url` is persisted as a queryable `Page` property in `database/ladybug/page.py` today;
closing this gap is new read/write surface on `LadybugGraphStore`; it is not a matter of
reshaping the two existing getters' output in `engine_core.py`.

## Corrections vs. the ticket's stated assumptions

- The ticket's example shape list ("visited, pending, depths, pages_crawled") is **BFS's**
  shape (`bfs_strategy.py`'s `pending` key), not BestFirst's. BestFirst uses `queue_items`
  (score/depth/url/parent_url dicts), confirmed distinct — see Q1 table above.
- The "priority-queue frontier need something different like scores" hedge in the ticket is
  correct: confirmed, `queue_items` entries carry `score` (negated internally for min-heap
  ordering — `bff_strategy.py:228,325` push `-score`, unpacked back to `-score` when read into
  `metadata["score"]` at `bff_strategy.py:293`) and `BFSDeepCrawlStrategy`'s `pending` shape has
  no such field.
- `_on_state_change` fires **per successfully-processed URL**, not per-level and not
  per-dequeue — batching (`BATCH_SIZE=10`) is purely an `arun_many` fetch-efficiency grouping,
  not a callback granularity; a failed page's dequeue never triggers the callback at all.
