# `dashboard/generic_template.py`

## module

The shared generic template every document without a dedicated Phase B
renderer falls back to (ADR-0016 point 2), ticket #123's second half.
Static HTML, plain Python string formatting - no templating dependency,
matching every other generator in this pipeline and ADR-0016 point 1's
own "no web/templating dependencies" constraint.

**Why one uniform `<pre>` block, not a kind-specific rendering.**
Syntax highlighting or Markdown-to-HTML would be exactly the
"per-document renderer" ADR-0016 point 2 reserves for a dedicated
integration that clears its own real bar (single vendorable asset,
actively maintained, meaningfully more effort saved). The generic
template's whole job is being the honest, uniform fallback for
everything that *doesn't* clear that bar - a half-good kind-specific
rendering here would blur that line, not serve it.

**Visual language matches the validated Phase C prototype**
(`prototype/dashboard-80`, ADR-0016) - the same dark palette and kind
badges, so Phase B's own pages read as part of one dashboard once
Phase C's shell wraps them.

## render_generic_page

Pure - `content` is the file's raw text, already read by the caller,
never read from `document.path` itself inside this function. The same
"generator returns content, the pipeline writes it" separation
`core/documents.py::DocumentGenerator` already enforces, kept here even
though this isn't a `DocumentGenerator`.

Carries its own breadcrumb back to `../concern/{document.name}.html`
(ticket #143) - the same `.name`/`.title` pair `dashboard/shell.py`
already groups documents by concern with, so no second lookup is
needed to know where "back" goes.
