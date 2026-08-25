# `spiders/browser/crawl4ai_crawler/session_aware_dispatcher.py`

## module

Ticket #246 on the "Adopt crawl4ai's native `BestFirstCrawlingStrategy` +
streaming" map (#245). Root cause, verified live against the installed
`crawl4ai==0.9.2` source rather than assumed from a workaround docstring:
`AsyncWebCrawler.arun()` only ever reads a session id off
`config.session_id` (`async_webcrawler.py:210,294,392,477`), but
`MemoryAdaptiveDispatcher.crawl_url` (`async_dispatcher.py:228`, shared by
both `run_urls` and `run_urls_stream`) passes `session_id=task_id` to
`arun()` as a bare keyword argument that's silently dropped - so every
concurrent fetch in a dispatcher batch or stream shares whatever
`session_id` the one `CrawlerRunConfig` handed to the dispatcher already
carried (`None`, falling back to `"default"`). Pragma's own `HookHandlers`
stashes each navigation's extraction under `config.session_id`
(`spiders/browser/crawl4ai_crawler/hooks.py`), so N concurrent fetches
racing to write/pop the same `"default"` stash entry silently
cross-attributes one page's components to another - the same bug
`spiders/orchestration/engine_core.py`'s own module docstring documents as
the reason it hand-rolls a worker pool instead of using this dispatcher
directly. This module is the fix at the source: the next ticket on #245
wires it into `PragmaBestFirstStrategy` so `engine_core.py`'s manual pool
can retire.

## SessionAwareDispatcher

Subclasses `MemoryAdaptiveDispatcher` and overrides only `crawl_url` -
the one place both `run_urls` (batch) and `run_urls_stream` (streaming)
already converge, since both call `self.crawl_url` rather than
duplicating its logic. Deliberately does not reproduce
`MemoryAdaptiveDispatcher.crawl_url`'s ~140 lines (memory-pressure
requeueing, rate limiting, monitor bookkeeping) to change the one thing
that's actually broken: it resolves `config` down to the single
`CrawlerRunConfig` matching `url` (`select_config`, crawl4ai's own
per-URL resolution), clones it with `session_id=task_id`, and hands that
already-resolved config to `super().crawl_url`, which re-resolves it as a
no-op (`select_config` returns a lone `CrawlerRunConfig` unchanged) before
running its own logic unmodified. Keeps this fix tied to crawl4ai's own
config-resolution behavior instead of a second, driftable copy of it -
if `crawl_url`'s internals change upstream, this override doesn't need to
track that change, only `select_config`'s contract.

## crawl_url

Same signature and return type as `MemoryAdaptiveDispatcher.crawl_url`.
The `None`-selected-config path (no config in a list matches `url`) is
preserved on its own: `select_config` returning `None` skips the
`.clone(...)` call, and `super().crawl_url` receives `None` exactly as
the base implementation's own `select_config(url, None)` call would
re-derive it (`isinstance(None, CrawlerRunConfig)` is `False`, `not None`
is `True`, so it returns `None` again) - the base's existing
no-config-match failure path (`CrawlStatus.FAILED`, a `"no_config_match"`
result) runs unchanged.
