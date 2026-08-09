---
name: component-catalog-skill
description: Narrate deterministic component facts into short human-readable documentation.
---
# Component Catalog Writer

## Task
You are given a page's worth of already-extracted, deterministic facts about its
interactive components - type, label, current state, and (where applicable) the
options/choices it offers. You are NOT looking at raw HTML and you are NOT
guessing at structure - every fact you're given is already verified true. Your
only job is to turn each into one short, clear documentation entry a human
product/QA reader can skim.

## Rules
- Write ONE entry per numbered component, in the same order given.
- Each entry: a short bold label (its type + short name), one or two sentences
  describing what it is and what it offers, then its current state.
- If `options`/`choices` are listed, name them (don't just say "has options") -
  and say which one is selected/default if marked.
- If it's part of a stepper (paired increment/decrement), describe the whole
  control as one unit, not three separate entries - name the current value.
- If it's part of a named choice group (radio/checkbox), describe the whole
  group as one unit, naming every member and which (if any) is checked.
- Never invent an option, state, or behavior that isn't in the given facts.
- Never mention CSS selectors, DOM paths, or implementation details - this is
  documentation for what the component *does*, not how it's built.
- If "interacted: false", say so plainly ("not yet exercised during this
  crawl") rather than omitting it.
- Keep each entry to 2-4 lines. No preamble, no summary section - just the
  numbered entries.
