# `generators/decisions_adr.py`

## module

`decisions.adr/` - one MADR-format decision record per `requirements.json`
entry classified `inferred`/`assumed`, docs/adr/0023.

**Only a minimal MADR subset.** Context and Problem Statement, then
Decision Outcome - no Decision Drivers/Considered Options, since pragma's
own classification rules are single-path heuristics, never a real
deliberation between named alternatives. Inventing options nobody
considered would fabricate exactly what this pipeline's own "never
invent, state the gap" discipline exists to avoid.

**Every output shares this generator's one title.** `ProducedDocument.title`
is set once per generator, not per output - `llms.txt`/`master.md` list
"Decision Records" once per file this generator writes, distinguished by
their own link (the numbered filename), not by their link text. Not
worth threading a per-output title through the pipeline for: ADR-0023
never asks for it, and `llms.txt`'s primary reader parses the raw line
(title *and* href together), not a rendered bullet list.

## _slug

Collision is harmless here - the sequential number prefix
(`0001-`, `0002-`, ...) is what actually disambiguates two files on
disk, so this only needs to read legibly, never to be unique on its own.

## decision_entities

Filters `requirements.json`'s own list to `inferred`/`assumed`
confidence, in that document's already-deterministic id order - never
crawl-discovery order, so the same crawl numbers its decisions
identically across runs.

## _render_decision

`_CONFIDENCE_CONTEXT` names the real reasoning per EARS pattern
(currently only `optional_feature` ever emits a non-`observed`
confidence, per `requirements.py`'s own module docstring); a pattern not
yet in that table gets an honest generic statement rather than a
fabricated specific one, so a future EARS-pattern addition doesn't
silently render nonsense.

## DecisionsAdrDocument

`kind="projection"` on every output - the same kind `_llms_section`
already routes to `## Optional` (ADR-0015), so this document lands there
without master_document.py needing a `decisions.adr`-specific rule.
