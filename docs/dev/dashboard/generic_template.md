# `dashboard/generic_template.py`

## module

The shared generic template every document without a dedicated Phase B
renderer falls back to (ADR-0016 point 2), ticket #123's second half.
Static HTML, plain Python string formatting - no templating dependency,
matching every other generator in this pipeline and ADR-0016 point 1's
own "no web/templating dependencies" constraint.

**Why one uniform `<pre>` block, not a kind-specific rendering.**
Syntax highlighting for CALM/CycloneDX/SARIF/etc. would be exactly the
"per-document renderer" ADR-0016 point 2 reserves for a dedicated
integration that clears its own real bar (single vendorable asset,
actively maintained, meaningfully more effort saved). The generic
template's whole job is being the honest, uniform fallback for
everything that *doesn't* clear that bar.

**Update - ticket #144 (map #142): Markdown is not one of those
formats.** It's nearly every `view`/`projection` document this
pipeline produces, not a rare exotic format with no good renderer -
staying stuck in the `<pre>` fallback showed a reviewer raw
`#`/`>`/`| --- |` syntax instead of the prose/tables it was meant to
be. `.md`-suffixed documents (checked by extension, not `kind` -
`llms.txt` is `kind="view"` too but isn't Markdown) now render through
`markdown` (`tables`/`fenced_code` extensions) and then `bleach.clean()`
- the second step isn't optional, since every document here ultimately
traces back to text scraped off a crawled site, and Python-Markdown
passes raw embedded HTML straight through by design.

**Visual language matches the validated Phase C prototype**
(`prototype/dashboard-80`, ADR-0016) - the same dark palette and kind
badges, so Phase B's own pages read as part of one dashboard once
Phase C's shell wraps them.

## _is_markdown

The extension, not `kind`, is the real signal - `llms.txt` is `kind="view"` too but isn't
Markdown.

## _render_markdown

Markdown-to-HTML via `markdown`, then `bleach.clean()` against a fixed `_ALLOWED_TAGS`/
`_ALLOWED_ATTRIBUTES` allowlist (structural tags this pipeline's own Markdown actually uses -
headers, tables, code, lists, links - nothing script/style/event-handler-capable). Pure Python,
no native wheel, deliberately - `ladybug`'s own C API gap is this project's one existing
native-dependency pain point, not worth a second one for a sanitizer.

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
