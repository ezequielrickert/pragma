# `spiders/browser/crawl4ai_crawler/mutation_heuristics.py`

## module

Flags a nominally-safe `GET` that likely mutates server-side state
despite the verb - an API that routes a delete/checkout/vote action
through `GET` (a real, if non-conformant, pattern this crawl has to
survive) rather than trusting the HTTP method alone to mean "safe to
call freely."

Two independent signals, either one enough: a method-override
(`_method`/`_http_method` query param, or an `X-HTTP-Method-Override`
header) naming a non-safe verb, or a mutating-verb token
(`delete`, `checkout`, `vote`, ...) found in the URL's path or query
string, camelCase-split first so `cancelOrder` matches the same as
`cancel_order` or `cancel-order`.

Pure and stateless on purpose - fixed built-in signals only, no
per-site configuration, no network call, no DOM access - so it can run
against a bare URL string before any request is actually sent, from
wherever a caller needs to decide whether a `GET` is safe to fire.
