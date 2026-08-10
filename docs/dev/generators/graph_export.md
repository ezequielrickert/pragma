# `src/generators/graph_export.py`

## module

Structured JSON export of a crawled site's graph - the machine-readable
counterpart to `GraphPRDSynthesizer`'s prose PRD and `component_tree.py`'s
ASCII tree, for a downstream tool (a dashboard, a diff script, another
pipeline) that wants the crawl's facts as data rather than as documents
meant for a person to read.

Same "reads only from `GraphStore`, writes nothing back" shape as
`component_tree.py` - pure, deterministic, no AI/LLM call anywhere in
this module (nothing here should ever need one: every field is already
structured fact sourced straight from `GraphStore`, not prose that needs
narrating). Kept as its own file rather than folded into
`graph_prd_synthesizer.py`/`component_tree.py` since its output audience
(another program) and its shape requirements (stable, parseable JSON)
are different enough from either that sharing a module would mean one
file serving two unrelated contracts.

## build_graph_export

Independently unit-testable without touching JSON serialization at all
(mirrors `component_tree.py`'s own build/render split, for the same
reason: assert on the structure, not on exact formatting).

Field-for-field, this is the same information `GraphPRDSynthesizer` and
`component_tree.py` already read to build their own documents - this
function adds no new `GraphStore` query, it just returns the raw
structures instead of turning them into prose or a tree.

## generate_graph_export_document

`sort_keys=True` so two exports of an identical graph state produce a
byte-identical file (a real `git diff` against a re-run of the same,
already-fully-crawled site shows nothing), same "deterministic
rendering" discipline `component_tree.py`'s `render_ascii_tree`
documents for the same reason.
