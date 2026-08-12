# `src/utils/urls.py`

## module

Per wiki/graph-based-crawl-tracking.md ("node identity is the whole
game - get canonicalization right or nothing else matters") and
wiki/browser-automation-pitfalls.md's redirect-normalization lesson.

Extracted from `SimplePRDGenerator._clean_url`
(`src/generators/prd_generator.py`) as a standalone function during the
crawl4ai migration, since the new mechanical crawler
(`src/crawlers/mechanical_loop.py`) needs it from more call sites than
the old single class did: crawl4ai's own `after_goto`/link extraction,
the interaction-frontier's page-key lookups, and eventually every
`GraphStore` call site once Phase 3 wires live writes. Logic - strip
scheme, `www.`, trailing slash, and fragment - so a URL reached via http
vs. https, www vs. bare domain, with vs. without a trailing slash, or
with vs. without a `#section` fragment, all collapse to the same key.

Confirmed live on empanad.app (see `debug_logs/`): the crawler tracked
`https://empanad.app` and `https://www.empanad.app/` as two distinct
`session_id`/frontier keys - each independently triggered the site's
per-visit "mint a new order" redirect, doubling the unbounded-frontier
problem `route_shape()` below exists to bound. `www.` stripping closes
that specific gap; it does not change identity for a site where `www.`
and bare are genuinely different hosts (rare, and not distinguishable
from this function alone - same tradeoff already accepted for scheme).

## _token_segment_re

A path segment that looks like an opaque, per-visit token (a session
id, order hash, tracking nonce) rather than a meaningful route slug:
long, alphanumeric-with-separators, and mixed enough (digits alongside
letters, or both cases) that it reads as generated rather than
human-authored. A real slug like "admisiones" or "about-us" is
all-lowercase-letters(+hyphen) and won't match; empanad.app's actual
tokens (`IJ_zXcXRtxGTl1_lxD-eR6BIcYJwLglV`, `HilNN6lA9xYMONnszrDuwxe2xIRbuzEM`,
...) do. Deliberately a heuristic, not a guarantee - see `route_shape`
below for how false negatives/positives are bounded by construction.

## _looks_generated

True if `segment` mixes digits or letter-cases the way a generated
token does (`IJ_zXcXRtxGTl1_lxD-eR6BIcYJwLglV`), rather than the
all-lowercase-letters(+hyphen) shape of a human-authored slug
(`admisiones`, `about-us`). Plain char scan, not a regex - no
lookahead/backtracking risk on an unbounded-length path segment.

## is_opaque_token

`_TOKEN_SEGMENT_RE.match(segment) and _looks_generated(segment)` as one
named, public function - `route_shape` (below) was the only caller for a
while, but `src/generators/request_family.py::normalized_endpoint`
(2026-08-12) needed the identical "does this look like a generated id"
judgment for API endpoint paths, not page paths - a dynamic order id in
`/rest/v1/orders/{id}/items` is the same kind of per-instance noise a
page's own session-token path segment is. Promoted here (was previously
just inlined in `route_shape`'s own list comprehension) so both callers
share one implementation instead of two copies that could drift.

## clean_url

Strips the fragment (everything from the first `#`), any trailing
slash, the scheme (`https://`/`http://`), and a leading `www.` - so
`https://www.example.com/x/#section` and `http://example.com/x` both
clean to `example.com/x`.

## route_shape

Canonicalize `url` one step further than `clean_url()`: collapse any
path segment that looks like an opaque per-visit token into a shared
`{token}` placeholder, so `example.com/o/<hash-a>` and
`example.com/o/<hash-b>` produce the *same* route shape.

Two legitimate uses, both in `MechanicalCrawler` - deliberately never a
third one:
- **Bounding the URL frontier** (`_enqueue`/`max_visits_per_route_shape`):
  how many literal instances of "the same kind of page" one crawl will
  keep visiting.
- **Canonical GraphStore/tracker identity** (`PageVisitor.visit`'s
  `page_key`): confirmed live on empanad.app that a session-token order
  flow is, to a human, obviously one screen - two visited hash
  instances should become one graph node with a merged component
  inventory, not two near-duplicate ones. `clean_url()` stays the
  identity used for every *physical-navigation* check (did the live
  browser session's literal URL change) - conflating the two there
  would mean a real navigation between two same-shaped hash instances
  (e.g. a "start a new order" button) stops being detected as a
  navigation at all, silently reusing selectors built for a page the
  session has already left. See `docs/dev/crawlers/page_visitor.md#visit`
  for the full split.

Never use this value as the literal URL to navigate to - it is lossy by
design (two structurally-different pages that happen to both have a
long opaque last segment collapse together too; accepted, since the
failure mode this guards against - an unbounded frontier, or N
duplicate nodes, on a session-token site - is far more costly than the
rare over-collapse).

## is_in_scope

Whether `url` belongs to the same site as `base_url` - the crawl's
starting point. This is a scope check for `MechanicalCrawler`'s URL
frontier, deliberately separate from `clean_url()`/`route_shape()`
identity above: a different *page* on the same *site* (or even a
different session-token instance of one) is always in scope; a
completely different *host* never is, regardless of how a link/redirect
got there.

Compares hosts only (via `clean_url()`'s own scheme/`www.`-stripping, so
`https://example.com` and `http://www.example.com` count as the same
host, consistent with every other identity check in this module) -
never the full `clean_url()`/`route_shape()` key, which also collapses
paths.

`allow_subdomains=False` (default): exact host match only - a crawl of
`example.com` does NOT follow a link to `blog.example.com`.
`allow_subdomains=True`: a naive last-two-label match -
`blog.example.com` counts as in-scope for a crawl of `example.com` (not
a full public-suffix-list lookup - same accepted limitation already
documented on `PragmaConfig.allow_subdomains`, e.g. this would also
accept `evil.co.uk` as in-scope for a crawl of `example.co.uk`, which a
real PSL lookup would correctly reject; not a concern for this
project's actual use case of scoping a single institutional/product
site).

An unparseable/empty host on either side fails *open* (returns `True`)
- this function is a scope backstop, not the primary identity check
(`clean_url()`), so a signal too weak to compare should never itself
block a crawl that would otherwise proceed - same "a weak/absent signal
should never trigger the riskier branch" discipline as
`component_matching.component_overlap_ratio`.
