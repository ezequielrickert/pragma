# Developer notes index

Every file under `src/` gets a matching file here, at the same relative path
(`src/crawlers/mechanical_loop.py` → `docs/dev/crawlers/mechanical_loop.md`).
The source file keeps a short (≤2-line) comment or docstring at each
decision point; anything longer - the "why," the bug it fixes, the
tradeoff it accepts - lives in the matching doc under a heading named
after the function/variable/branch it explains, and the source points at
it with a one-line `Details:` pointer:

```python
# Deliberately not the same guard as X - see this variable's own note.
# Details: docs/dev/crawlers/page_visitor.md#stale-resynced-since-success
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
| `src/crawlers/component_matching.py` | [component_matching.md](crawlers/component_matching.md) |
| `src/crawlers/interaction_tracker.py` | [interaction_tracker.md](crawlers/interaction_tracker.md) |
| `src/crawlers/visit_result.py` | [visit_result.md](crawlers/visit_result.md) |
| `src/crawlers/page_extraction.py` | [page_extraction.md](crawlers/page_extraction.md) |
| `src/crawlers/debug_log.py` | [debug_log.md](crawlers/debug_log.md) |
| `src/crawlers/network_filter.py` | [network_filter.md](crawlers/network_filter.md) |
| `src/crawlers/fill_values.py` | [fill_values.md](crawlers/fill_values.md) |
| `src/crawlers/fill_value_agent.py` | [fill_value_agent.md](crawlers/fill_value_agent.md) |
| `src/crawlers/graph_sink.py` | [graph_sink.md](crawlers/graph_sink.md) |
| `src/crawlers/mechanical_loop.py` | [mechanical_loop.md](crawlers/mechanical_loop.md) |
| `src/crawlers/page_visitor.py` | [page_visitor.md](crawlers/page_visitor.md) |
| `src/crawlers/crawl4ai_crawler.py` | [crawl4ai_crawler.md](crawlers/crawl4ai_crawler.md) |
| `src/core/interfaces.py` | [interfaces.md](core/interfaces.md) |
| `src/core/engine.py` | [engine.md](core/engine.md) |
| `src/core/config.py` | [config.md](core/config.md) |
| `src/core/wizard.py` | [wizard.md](core/wizard.md) |
| `src/core/app.py` | [app.md](core/app.md) |
| `src/core/bootstrap.py` | [bootstrap.md](core/bootstrap.md) |
| `src/core/prompts.py` | [prompts.md](core/prompts.md) |
| `src/cli.py` | [cli.md](cli.md) |
| `src/storage/neo4j_graph_store.py` | [neo4j_graph_store.md](storage/neo4j_graph_store.md) |
| `src/storage/memory_graph_store.py` | [memory_graph_store.md](storage/memory_graph_store.md) |
| `src/generators/component_classifier.py` | [component_classifier.md](generators/component_classifier.md) |
| `src/generators/component_tree.py` | [component_tree.md](generators/component_tree.md) |
| `src/generators/graph_export.py` | [graph_export.md](generators/graph_export.md) |
| `src/generators/graph_prd_synthesizer.py` | [graph_prd_synthesizer.md](generators/graph_prd_synthesizer.md) |
| `src/utils/io.py` | [io.md](utils/io.md) |
| `src/utils/urls.py` | [urls.md](utils/urls.md) |
| `src/agents/local_agent.py` | [local_agent.md](agents/local_agent.md) |
