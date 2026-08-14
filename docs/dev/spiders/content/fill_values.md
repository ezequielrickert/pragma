# `spiders/content/fill_values.py`

## module

Fill-value generation for mechanically-discovered form fields - the
deterministic Phase 2 default and the Phase 4 AI-backed real implementation
both live behind the same async signature, `(component, page_description) ->
str`, so `MechanicalCrawler` never has to know which one it was given.

Split into its own module (rather than living in `mechanical_loop.py` or
`fill_value_agent.py`) specifically so both of those can import
`default_placeholder_fill_value` - the AI path falls back to it on failure -
without an import cycle between them.

## default_placeholder_fill_value

Deterministic, non-AI placeholder fill value - Phase 2's original default,
and Phase 4's fallback when a live AI call fails or is unavailable. Never
the empty string, so a fill's "did this land" signal (the live `value`
field on re-discovery) is always unambiguous even with this placeholder in
place. `page_description` is accepted and ignored - kept in the signature
purely so this is interchangeable with `fill_value_agent.generate_fill_value`
at every call site.
