# `generators/gherkin.py`

## module

D8: BDD scenarios, and the sequence diagram each one already is.

**The model names, and never writes a step.** Every Given/When/Then is
rendered from a recorded trace. A scenario whose steps the model wrote
would be a plausible story about the application rather than a record of
it - and the point of this document is that a runner can execute it
against the rebuild, which requires the steps to be true.

**Honest about its own shape.** The crawl is exhaustive, not
goal-directed, so these are scenarios of what *can* be done rather than of
what a user sets out to do. Traces are short because a pass stops the
moment an interaction navigates - which is also what makes that cut a
natural scenario boundary rather than an arbitrary one.

**Traceability tags (docs/adr/0013), added in ticket #107.** `@REQ-<hash>`
and `@confidence:observed` are required on every scenario this document
writes; a trace correlating to no `requirements.py` extraction rule is
excluded rather than tagged with something invented. `Background` is
deliberately never used - it needs a real precondition common to every
scenario in one `Feature`, and this crawl has no state/authentication
instrumentation to back one honestly. The correlation itself (a store
read, `requirements.py`/`core.graph_metrics` calls) lives in
`generators/gherkin_tags.py` - see `docs/dev/generators/gherkin_tags.md` -
once it made this module cross the file-size-audit SPLIT threshold; this
module stays a pure trace-shape renderer, no store dependency.

## _is_observable

A pass whose every interaction changed nothing and called nothing is real
crawl history and an empty specification. Keeping those would bury the
scenarios that assert something under ones that assert nothing.

## _quoted

Gherkin delimits a step's arguments with double quotes, so one inside a
button's own label (`Buy "now"`) closes the argument early and corrupts
the file. Replaced with single quotes rather than escaped: the label is
being quoted for a human to read, not round-tripped.

## _table_cell

The `Examples:` table's own delimiter is `|`, not `"` - a value containing
one (rare, but a label could) would otherwise be read as a column break.
Newlines are flattened to a space for the same "one physical row" reason.

## render_scenario

No tag line: the caller prepends one (`GherkinDocument.generate`), because
the identical body is also `render_scenario_outline`'s template - keeping
tagging out of this function means neither caller has to strip anything.

## render_sequence_diagram

The H4 item from the plan, and it costs nothing: a trace already *is* a
sequence - actor, control, endpoint, response, over time - so this is the
same data drawn rather than a second query. That also means the diagram
cannot disagree with the scenario above it.

## narrate_titles

One call per scenario, for a title. The system instruction says plainly
not to invent a step, but the real guarantee is structural: the steps are
rendered before the model is consulted and are not derived from its
answer at all.

A failed call degrades that one title to `_fallback_title`, which is built
from the trace itself - poorer to read, and never wrong.

## _structural_signature

The `template_hash` idea (`generators/aria_tree.py::_structural_shape`,
ADR-0003) applied to a trace: strip every concrete value, keep the shape.
Per step: the route (not the literal page), the action, the label (kept,
not stripped - two traces differing only in *which* control was clicked
are a different pattern, not the same one with a different value), what
it fired (method + route + status + failed, never the literal url or
query string), and which route it navigated to (`""` if it didn't).

The destination is a per-step route, not one trailing "did it navigate"
boolean - two traces landing on genuinely different routes are different
patterns even though both technically "navigated somewhere."

## _group_by_pattern

First-seen order, not sorted by signature - so the `.feature` file's
scenario order still roughly follows crawl order rather than jumping
around by hash.

## _templated_trace

Builds one synthetic `Trace` for a group's `Outline` body: every field
that's constant across the group stays literal, every field that varies
becomes a `<placeholder>` token. Because a Gherkin placeholder is just
literal `<name>` text sitting where a value normally would, this synthetic
trace renders correctly through `render_scenario` unchanged - no second,
templated rendering path was needed.

## _placeholder_row

The `Examples:` row one member trace contributes, one dict per member.
Every trace in a group produces the same key set: the group already
shares one structural signature, so the *positions* that vary are
identical across every member, only the concrete values differ.

## render_scenario_outline

`Scenario Outline` + `Examples` (ADR-0013 point 4) for a group of 2+
structurally identical traces - one templated body, one concrete row per
occurrence, instead of N near-duplicate `Scenario`s a reader has to
notice are the same thing.

## GherkinDocument

`extension = "feature"`, and the output is a **real** `.feature` file:
comments as `#` lines, then `Feature:`, then scenarios. An earlier version
embedded the Gherkin in a fenced block inside Markdown, which reads fine
and cannot be executed - defeating the document's whole reason to exist.

Verified by parsing the generated output with the official Cucumber
parser (`gherkin-official`) rather than by asserting substrings, so a
malformed step fails the test rather than passing a `"Given" in text`
check.

## SequenceDiagramsDocument

Registered separately because one generator writes one file and the two
have different formats - a `.feature` cannot hold a Mermaid block, and a
Markdown file cannot be run by Cucumber. They share `_observable_traces`
and `_titles_for`, so the diagram and the scenario always describe the
same trace under the same name.
