# Developer notes index

Every file under a top-level Python package (`core/`, `agents/`, `database/`, `spiders/`,
`generators/`, `utils/`) gets a matching file here, at the same relative path
(`spiders/orchestration/mechanical_loop.py` → `docs/dev/spiders/orchestration/mechanical_loop.md`).
The source file keeps a short (≤2-line) comment or docstring at each
decision point; anything longer - the "why," the bug it fixes, the
tradeoff it accepts - lives in the matching doc under a heading named
after the function/variable/branch it explains, and the source points at
it with a one-line `Details:` pointer:

```python
# Deliberately not the same guard as X - see this variable's own note.
# Details: docs/dev/spiders/orchestration/page_visitor.md#stale-resynced-since-success
```

**Why split it this way:** reading the code should read like code - a
short comment tells you *that* something is deliberate and where to go if
you need the story; it doesn't make you read the story to find the next
line of logic. The full story isn't deleted, just moved somewhere you
open on purpose, not somewhere you scroll past.

**Anchor convention:** each heading in a doc file is named after the
exact symbol it documents (a function name, a class name, a specific
local variable, or a short slug for a branch/comment that has no name of
its own) so the `Details:` pointer's anchor is predictable from the code
alone. Headings use `##`; GitHub/most Markdown renderers turn `## Some
Heading` into anchor `#some-heading` automatically (lowercase, spaces to
hyphens, punctuation stripped).

**Keeping this in sync:** touch the doc file in the same change that
touches the code it describes - a stale `Details:` pointer or a doc
section describing behavior the code no longer has is worse than no doc
at all. This directory covers *why this code is shaped the way it is*;
see `wiki/` instead for durable, project-independent lessons, and (once
revived) `docs/explicativos/` for prose walkthroughs of a whole subsystem
aimed at onboarding rather than a specific line of code.

## Index

| Source file | Doc |
|---|---|
| `spiders/browser/crawl4ai_crawler.py` | [crawl4ai_crawler.md](spiders/browser/crawl4ai_crawler.md) |
| `spiders/browser/debug_log.py` | [debug_log.md](spiders/browser/debug_log.md) |
| `spiders/browser/dom_settle.py` | [dom_settle.md](spiders/browser/dom_settle.md) |
| `spiders/content/component_matching.py` | [component_matching.md](spiders/content/component_matching.md) |
| `spiders/content/fill_value_agent.py` | [fill_value_agent.md](spiders/content/fill_value_agent.md) |
| `spiders/content/fill_values.py` | [fill_values.md](spiders/content/fill_values.md) |
| `spiders/content/network_filter.py` | [network_filter.md](spiders/content/network_filter.md) |
| `spiders/content/page_extraction.py` | [page_extraction.md](spiders/content/page_extraction.md) |
| `spiders/orchestration/graph_sink.py` | [graph_sink.md](spiders/orchestration/graph_sink.md) |
| `spiders/orchestration/interaction_tracker.py` | [interaction_tracker.md](spiders/orchestration/interaction_tracker.md) |
| `spiders/orchestration/mechanical_loop.py` | [mechanical_loop.md](spiders/orchestration/mechanical_loop.md) |
| `spiders/orchestration/measurement_pass.py` | [measurement_pass.md](spiders/orchestration/measurement_pass.md) |
| `spiders/orchestration/page_visitor.py` | [page_visitor.md](spiders/orchestration/page_visitor.md) |
| `spiders/orchestration/visit_result.py` | [visit_result.md](spiders/orchestration/visit_result.md) |
| `core/interfaces.py` | [interfaces.md](core/interfaces.md) |
| `core/engine.py` | [engine.md](core/engine.md) |
| `core/config.py` | [config.md](core/config.md) |
| `core/wizard.py` | [wizard.md](core/wizard.md) |
| `core/app.py` | [app.md](core/app.md) |
| `core/bootstrap.py` | [bootstrap.md](core/bootstrap.md) |
| `core/prompts.py` | [prompts.md](core/prompts.md) |
| `cli.py` | [cli.md](cli.md) |
| `database/neo4j_graph_store.py` | [neo4j_graph_store.md](database/neo4j_graph_store.md) |
| `database/memory_graph_store.py` | [memory_graph_store.md](database/memory_graph_store.md) |
| `generators/component_classifier.py` | [component_classifier.md](generators/component_classifier.md) |
| `generators/component_tree.py` | [component_tree.md](generators/component_tree.md) |
| `generators/graph_export.py` | [graph_export.md](generators/graph_export.md) |
| `generators/graph_prd_synthesizer.py` | [graph_prd_synthesizer.md](generators/graph_prd_synthesizer.md) |
| `utils/io.py` | [io.md](utils/io.md) |
| `utils/urls.py` | [urls.md](utils/urls.md) |
| `agents/local_agent.py` | [local_agent.md](agents/local_agent.md) |
