# `src/generators/gherkin.py`

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

## _is_observable

A pass whose every interaction changed nothing and called nothing is real
crawl history and an empty specification. Keeping those would bury the
scenarios that assert something under ones that assert nothing.

## _quoted

Gherkin delimits a step's arguments with double quotes, so one inside a
button's own label (`Buy "now"`) closes the argument early and corrupts
the file. Replaced with single quotes rather than escaped: the label is
being quoted for a human to read, not round-tripped.

## render_scenario

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
