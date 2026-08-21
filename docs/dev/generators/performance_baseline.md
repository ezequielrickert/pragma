# `generators/performance_baseline.py`

## module

`performance-baseline.json` - network latency aggregates per distinct
`template_hash`, Core Web Vitals reserved, docs/adr/0026.

**Why per template, not per screen.** Near-identical pages sharing one
`tree.aria.yaml` structural template have near-identical performance
characteristics - measuring every `SCR-<hash>` instance independently
would be redundant, and `tree`'s own dedup mechanism (ADR-0003) already
solves exactly this shape of problem. Every screen with a captured
snapshot gets a template entry regardless of whether any of its
requests carry a measured latency - `network.sample_count: 0` says so
honestly rather than the template being silently absent.

## _percentile

Nearest-rank, no interpolation - a simple, unambiguous definition so
p50/p95/p99 are reproducible across Python versions without depending
on `statistics.quantiles`'s own interpolation method choice.

## _network_aggregate

All three percentiles `null` (never a fabricated `0`) when a template
has no measured latency sample yet.

## _group_by_template

`{template_hash: [SCR-<hash>, ...]}` - every screen sharing one
structural template.

## _latencies_by_template

Attributes each measured `Request.latency_ms` to the template of the
page it was observed on. A request on a page with no captured
accessibility snapshot contributes nothing - there is no known template
to attribute it to, and inventing one would misrepresent the data.

## build_performance_baseline

Reads `aria_tree.template_hash_by_page` and
`GraphStore.get_request_latencies_by_page` directly - the real sources,
never a second, independently-derived grouping.

## _render_performance_baseline_view

Mechanically rendered from `performance-baseline.json`'s own entries -
never hand-authored in parallel with it.

## PerformanceBaselineDocument

Source (`performance-baseline.json`, schema-validated) + view
(`performance-baseline.md`) split.
