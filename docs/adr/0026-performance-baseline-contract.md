# `performance-baseline` reuses tree's template dedup, stays pragma-native

**Status**: accepted

The ticket's three open points resolve against what's actually instrumented today and what's
already been solved once. `Request.latency_ms` (`database/ladybug/schema.py`) is real, per-request
network timing captured now; Core Web Vitals (LCP, FCP, CLS, INP, TTFB) need browser-side
Performance API instrumentation that doesn't exist yet — confirmed against the codebase, not
assumed. And the granularity question `tree` already answered for a structurally identical problem:
near-identical pages don't need independent treatment.

Decided, resolving the ticket's three open points:

**1. What Ships Real vs. Reserved.** Network-level latency aggregates (p50/p95/p99 of
`Request.latency_ms`, computed from data the crawler already gathers) ship as real v1 data. Core
Web Vitals ship as **reserved** fields — present, typed, empty until Playwright's Performance
API/CDP is wired to capture them. Not a permanent gap: Playwright can capture these, pragma just
doesn't yet, the same reserved-field posture `coverage` (ADR-0001) and `risk-register` (ADR-0024)
already established for real-but-uninstrumented data.

**2. Granularity: Per Template, Not Per Screen.** Baselines are computed per distinct `template_hash`
(`tree`, ADR-0003), not per individual `SCR-<hash>` instance and not a hand-curated "representative
pages" list. Near-identical pages sharing a template have near-identical performance characteristics
— measuring every instance would be redundant, and a manually-curated sample would need HITL
curation this ticket has no reason to require when a dedup mechanism already exists for exactly this
shape of problem.

**3. Format: Pragma-Native, Web Vitals' Own Metric Names Where They Apply.** Not Lighthouse CI's
full report format — Lighthouse bundles performance scoring together with accessibility, SEO, and
best-practices scoring, which would reintroduce the overlap this map has deliberately avoided
everywhere else (`accessibility.json` already owns a11y scoring, ADR-0012). `performance-baseline.json`
uses Web Vitals' own metric names and units (LCP, FCP, CLS, INP, TTFB) for the browser-rendering
metrics specifically — their actual authoritative naming — plus pragma-specific fields for the
network-latency aggregates Web Vitals has no equivalent for.

Wayfinder ticket: [performance-baseline: lock Web-Vitals/Lighthouse-shaped contract](https://github.com/ezequielrickert/pragma/issues/90),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
