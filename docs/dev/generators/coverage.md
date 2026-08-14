# `generators/coverage.py`

## module

How much of the site the crawl reached - both as its own document (D9 in
`research/plan-generacion-de-documentos.md`) and as the banner every
Markdown document opens with.

**Why it is on every document and not just its own.** Every generator
here describes what the crawl found. None of them can describe what it
never reached, and none of them look any different for it: an OpenAPI
contract inferred from 40% of an application is shaped exactly like one
inferred from all of it. The banner is the difference between an artifact
that is incomplete and one that is misleading.

This is also the number that decides where effort pays off. If the plan's
later phases produce a thin OpenAPI document, the question "is the
generator weak, or did the crawl only see a third of the app?" has to be
answerable without re-running anything.

## public_surface_caveat

Stated on every document because the crawl does not sign in - the login
helper writes a session file that nothing reads (see
`research/plan-generacion-de-documentos.md` H3, and the decision there not
to wire it for now).

The wording matters: pages behind authentication are **absent and not
counted as missing**. They never enter the frontier, so they are not in
`pages_total` either - "2/2 pages, 100%" on an application with an admin
area is a true statement about the crawl and a false impression about the
application, unless the scope is stated alongside it.

## CrawlCoverage

Percentages are properties rather than stored fields so the record holds
only measurements, and anything derived from them is computed at the point
of display. Nothing can drift out of sync with its own numerator.

## _percent

An empty crawl reports 0%, not `ZeroDivisionError`. A site where nothing
was recorded is a real outcome - a dead URL, a crawl that failed on its
first navigation - and the coverage report is precisely the document that
should still render in that case, since it is the one that explains why
everything else is empty.

## build_coverage

Reads `count_visited`, `count_unexplored_components`,
`get_progress_table_rows` and `get_inferred_requests` - four existing
queries, no new store surface. `components_explored` is derived by
subtraction because the store counts *unexplored*, which is what the crawl
frontier needs; the document wants the complement.

## render_coverage_banner

A Markdown blockquote, so it renders as a visually distinct callout on
GitHub and in any Markdown viewer rather than reading as the document's
first paragraph.

## CoverageDocument

Lists unfinished URLs explicitly rather than only counting them. A count
tells you coverage is incomplete; the list tells you *what* is missing, so
a reader who knows the application can immediately judge whether the gap
matters - a forgotten `/legal` page and a missed checkout flow produce the
same percentage.
