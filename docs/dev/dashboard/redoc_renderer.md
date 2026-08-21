# `dashboard/redoc_renderer.py`

## module

Redoc integration for `openapi.yaml` - the one document Phase B's own
reuse audit found clears ADR-0016 point 2's bar, ticket #124.

**Why CDN-pinned, not vendored.** Vendoring a multi-hundred-KB
third-party bundle into a Python-only backend repo adds real weight and
a re-vendor step on every Redoc release, for a benefit (offline viewing
of this one page) neither audience this dashboard serves actually
needs - Claude Code reads `openapi.yaml` itself directly, never through
Redoc's rendering, and a human reviewer with no network access still
has the same raw file to read. Pinned to major version 2 (`redoc@2` on
jsDelivr) rather than a specific patch - stating a precise patch number
without a way to verify it's current would be fabricated specificity;
the major-version pin still protects against a breaking v3.

**Why the spec is embedded inline, not fetched by `spec-url`.** A
browser's `file://` security model often blocks a real HTTP(S) fetch
for a page opened directly - the same constraint that ruled out a live
process anywhere in ADR-0016's own architecture. Parsed from YAML to a
dict (`yaml`, already a project dependency) and re-embedded as a
`<script type="application/json">` block instead.

## render_redoc_page

Same signature/style as `generic_template.render_generic_page` -
`content` is the caller-supplied raw text, never read from disk here.
Carries the same breadcrumb back to `../concern/{document.name}.html`
(ticket #143) that `render_generic_page` does.
