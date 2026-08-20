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

`interactions_triggered` and `saturation_curve` (docs/adr/0001) joined the
original fields when `coverage.json` became a real source document
(ticket #96): how many interactions actually fired, and how many
first-party endpoints were still new at each one - the ADR's own "honest
substitute for a percentage" for API surface, which has no known
denominator.

## _percent

An empty crawl reports 0%, not `ZeroDivisionError`. A site where nothing
was recorded is a real outcome - a dead URL, a crawl that failed on its
first navigation - and the coverage report is precisely the document that
should still render in that case, since it is the one that explains why
everything else is empty.

## _saturation_curve

One point per interaction, not a coarser bucket - the schema names the
shape but not a bucket size, and inventing one here would be an
aggregation choice this generator has no basis to make. Reads
`get_endpoint_discovery_sequence`'s own crawl-order sequence, so "new
endpoints" means new *at that point in the crawl*, not sorted by anything
else.

## build_coverage

Reads `count_visited`, `count_unexplored_components`,
`get_progress_table_rows`, `get_inferred_requests`,
`count_interactions`, and `get_endpoint_discovery_sequence` - the last
two added for `interactions_triggered`/`saturation_curve` (ticket #96).
`components_explored` is derived by subtraction because the store counts
*unexplored*, which is what the crawl frontier needs; the document wants
the complement.

## _coverage_document

`coverage.json`'s full payload (`schemas/coverage.schema.json`,
docs/adr/0001): `coverage`'s graph-derived numbers plus the run-level
facts (`run_id`/`target`/`duration_s`) `build_coverage` has no access to,
threaded through `request.settings` by `core/engine.py`.
`roles`/`blockers`/`module_coverage` are reserved per the ADR - minimal
real defaults (`["anon"]`, `[]`, `[]`), not invented data.

## render_coverage_banner

A Markdown blockquote, so it renders as a visually distinct callout on
GitHub and in any Markdown viewer rather than reading as the document's
first paragraph.

## _render_coverage_view

`coverage.md` - the human-readable view `coverage.json` was split out of
(ticket #96, docs/adr/0001's source/view distinction). Mechanically
rendered from the same `CrawlCoverage` the JSON source uses, so the two
files can never disagree with each other about the numbers, only about
how they're presented.

## CoverageDocument

Two outputs since ticket #96: `coverage.json` (`kind="source"`, schema-
validated) and `coverage.md` (`kind="view"`) - `generate()` returns both
as a `Tuple[DocumentOutput, ...]`, the multi-file contract `core/documents.py`
added (docs/adr/0030).

`coverage.md` lists unfinished URLs explicitly rather than only counting
them. A count tells you coverage is incomplete; the list tells you *what*
is missing, so a reader who knows the application can immediately judge
whether the gap matters - a forgotten `/legal` page and a missed checkout
flow produce the same percentage.
