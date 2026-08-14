# `spiders/content/fill_value_agent.py`

## module

Phase 4 of the crawl4ai migration: AI-generated fill values for
mechanically-discovered form fields - the one AI call that happens
*during* the mechanical crawl itself (every other AI use is post-hoc,
Phase 5).

## FILL_VALUE_SYSTEM_INSTRUCTION

Its own, narrowly-scoped instruction - per
wiki/prompt-engineering-for-llm-agents.md Principle 1 ("never share a
system_instruction across semantically different calls"), it is not
reused from anywhere else, and nothing else should reuse it either: its
only job is "given one field's metadata, return one plausible value,"
nothing about narration, synthesis, or any other call site this migration
adds.

## generate_fill_value

`Agent.generate()` is a synchronous call (most backends are blocking HTTP
requests; local ones can be genuinely slow - see
wiki/local-and-small-model-constraints.md's generous-timeout guidance) -
run via `asyncio.to_thread` so a live AI call never blocks the mechanical
crawl's own event loop while it waits, and other pages' work isn't
serialized behind it unnecessarily.

Falls back to `default_placeholder_fill_value` - never raises up into the
caller - on any agent failure or an empty/unusable response, matching
wiki/local-and-small-model-constraints.md's "recover, don't error"
guidance for a parameter the model might mishandle: one bad or slow model
response must not abort an otherwise-mechanical crawl.

## make_ai_fill_value_fn

Bind `agent` into a `fill_value_fn` closure matching `MechanicalCrawler`'s
expected `(component, page_description) -> str` signature - the
convenience constructor callers pass to
`MechanicalCrawlerConfig(fill_value_fn=make_ai_fill_value_fn(my_agent))`.
