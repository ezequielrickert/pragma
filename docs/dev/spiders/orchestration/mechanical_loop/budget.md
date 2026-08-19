# spiders/orchestration/mechanical_loop/budget.py

## module

How much one run is allowed to do before it stops and hands the rest over.

A run ends for one of two reasons: the frontier drained (the site is done), or a
budget tripped (this slice is done, the rest stays `Pending` for the next run).

**"One long run" is not a mode, it is `None`.** With every budget unset the
second reason never fires and the behaviour is exactly what it was before
budgets existed, on the same code path. That is the point: a separate
"unlimited" mode would be a second path that drifts from the budgeted one, and
`--full` clears the budgets rather than branching.

## crawlbudget

Independently optional caps. Each is `None` by default, and any combination is
valid - they are checked together, not as alternatives.

## budgettracker

Counts a run's work against a `CrawlBudget` and names what tripped.

**It owns its own start time** so a caller cannot forget to set one. A tracker
whose clock started whenever someone remembered to call `start()` would report a
minutes budget that is quietly wrong, and wrong in the direction of running
longer.

The reason is reported as **text**, not an enum, because the only consumer is a
person reading why their crawl stopped early - it reaches them through the
coverage banner on every generated document, so a partial document says which
budget cut it short rather than looking complete.

## minutes

Worth setting even when `pages` is what you actually mean, and this is the
lesson a 12-hour run taught: **a page whose DOM keeps producing new components
finishes no page at all**. A page-only budget never trips in that case, because
the counter it watches never advances. The minutes cap is the one that returns
the terminal.

## exhausted_reason

Which cap tripped, or `None` while there is room left.

Checked in declaration order, so a run that trips two at once reports the page
count - the cap an operator most likely set on purpose, rather than the backstop
that happened to fire in the same tick.
