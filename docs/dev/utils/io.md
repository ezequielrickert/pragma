# `utils/io.py`

## record_run_manifest

Append one run's metadata to a shared, git-diffable manifest under
`out_dir` (`{out_dir}/runs.json`) - `{site: [entry, ...]}`, oldest first.

Every other output document `Engine` writes (PRD, component tree, JSON
export) is timestamped in its own *filename*, which is enough to keep
runs from colliding but not enough to answer "what's the latest run for
this site" or "what runs exist at all" without listing the directory
and parsing filenames - this manifest is that missing index, cheap to
keep since `Engine` already builds every field it needs as a side
effect of finishing a run.

Deliberately one shared file across every site (not one manifest per
site) - a single small JSON file is easy to `git diff`/inspect whole,
and the number of sites one project tracks is small enough that this
never becomes a hot file the way `docs/{site}_*` output files already
aren't (those keep growing with every run regardless of this manifest).

Not safe against two processes writing concurrently (read-modify-write,
no file lock) - acceptable for how this project runs today (one
`Engine` per process, one CLI invocation at a time); if concurrent runs
against the same `out_dir` ever become a real usage pattern, this needs
a lock or a per-run-file-plus-rebuild scheme instead of a single shared
file.

The corrupted-manifest catch: a corrupted/partial manifest must never
block a real crawl from finishing and writing its actual output - start
a fresh manifest instead of raising, same "documentation enrichment,
not something correctness depends on" discipline
`GraphPRDSynthesizer`'s narration failure handling already uses.

## generate_docs_index

Render `{out_dir}/runs.json` (`record_run_manifest`) as a browsable
Markdown index - one table per site, most recent run first, linking to
each run's own PRD/tree/JSON-export files by their (already-relative,
same-directory) filename.

docs/explicativos/plan-almacenamiento.md Fase E: evaluated standing up
a full `mkdocs-material` static site for this (item 12 of the plan) and
deliberately chose this instead - a handful of Markdown files per site
is not enough volume to justify a new heavyweight dependency plus a
build step; a single generated Markdown index, viewable directly on
GitHub or in any Markdown-aware editor with zero extra tooling, solves
the actual "I can't find last week's run for this site" problem this
was asked to solve. Revisit if `docs/` output ever grows
large/complex enough that a real search/filter UI would earn its cost.

Pure function of `runs.json`'s already-persisted content - no
`GraphStore` access, no AI, no browser - same "deterministic, no
ceremony" shape as `component_tree.py`/`graph_export.py`'s own
top-level entry points.

The corrupted-manifest catch mirrors `record_run_manifest`'s own: a
broken index is a degraded index, not a reason to fail whatever called
this.
