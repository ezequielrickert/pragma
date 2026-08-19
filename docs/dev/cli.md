# `cli.py`

## main

Bare `python3 cli.py` from a real terminal launches the interactive
menu app (navigate between analyzing a URL and configuring the
pipeline, no flags needed). `python3 cli.py config` jumps straight
to the setup wizard. Any other invocation (flags/positional URL) runs a
single analysis directly, for scripting/automation.

## _print_documents

Lists every document a finished run wrote, master document first.

**Why master first and not in list order.** It indexes the others and
carries the coverage numbers, so it is the file to open. Printed in
pipeline order it lands *last*, and printed alphabetically it lands in the
middle - either way it reads as one more filename, which is exactly the
"which of these ten do I open" problem it exists to solve.

**Why it iterates `result.documents` instead of printing a line per named
field.** The CLI was the last place still carrying one hardcoded line per
output file - the same shape Fase 0 deleted from `Engine`. Iterating means
a document added by a later phase shows up here on its own, and it is why
`coverage` and `master` were missing from this output when they first
landed.

The empty case prints an explicit "No documents were generated" rather
than nothing: every generator failing is survivable by design (the
pipeline degrades per document), and a silent success would be
indistinguishable from a run that worked.

## _apply_budget_flags

Folds the three run-budget flags into `config.crawl_budget`.

Kept out of the generic override dict because they are not `PragmaConfig` fields
in their own right - they edit keys *inside* one field, and `--full` clears
rather than sets.

`--full` wins outright. It is the "ignore what the YAML says, run the whole
thing" escape hatch, so combining it with a limit is a contradiction, resolved in
its favour rather than by erroring - an operator who typed both wants the long
run.
