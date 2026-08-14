# `generators/component_family_narrator.py`

## module

Adds a one-sentence "what is this pattern used for" `purpose` to each
already-clustered `ComponentFamily` (see `component_family.md` for how
clustering itself works) - e.g. "confirms or submits an action" for a
family whose members say "Confirmar"/"Aceptar", "adjusts a numeric
quantity up or down" for a stepper's +/- pair.

Deliberately a separate file from `component_family.py`: that module
commits, in its own module docstring, to being pure/no-I/O/no-LLM - this
is the impure half of the same overall feature, needing an `Agent` to
actually write the sentence. Mirrors `graph_prd_synthesizer.py`'s own
per-item narration pattern (`_narrate_page_catalog`): one
`agent.generate()` call per thing being described, a failure on one item
degrades just that item rather than aborting the pass.

## purpose_system_instruction

Explicitly told to describe *functional* purpose only, never visual
appearance (color/size/CSS) or implementation detail (selectors/paths) -
same "describe it the way a person looking at the page would, not a
developer" instruction shape `CATALOG_SYSTEM_INSTRUCTION`
(`graph_prd_synthesizer.py`) already uses for page-level narration. Also
told to say plainly when the member texts don't suggest a clear common
purpose, rather than inventing a plausible-sounding one - the same
"don't invent facts" discipline every system instruction in this project
uses.

## narrate_family_purposes

Args are `agent`, `families` (the pure clustering step's own output -
`purpose` is still `""` on every entry when this receives them), and
`member_texts` - a `{(page_url, path): text}` lookup the caller builds
from the same `get_component_ledger` read that fed `build_component_
families` in the first place. `ComponentFamily.member_paths` only
carries identity (which page, which selector), never each member's own
visible text - `component_family.py` was kept deliberately lean, so the
text has to come back in from the caller instead of being duplicated
into the dataclass itself.

Skips the `agent.generate()` call entirely for a family whose members
have no text at all (nothing meaningful to narrate - the call would just
be spent asking the model to describe blank input). A failed call leaves
`purpose` at `""` for that one family and moves on to the next - see
`Engine._apply_component_families` for where this is called from
(`core/engine.py`), always right after clustering and before the
result is written to `GraphStore`.

**Verified against real narration** (a deterministic stub agent, not a
live API call, run against empanad.app's already-crawled data): every
family with member text got a distinct, correct-reading purpose -
`"Adjusts a numeric quantity up or down."` for the +/- stepper pair,
`"Adds an item to the order."` for the "Agregar" family, `"Confirms or
submits an action."` for the submit-button family. Families whose only
members are unlabeled text inputs (no visible text on any member)
correctly stayed at `purpose=""` rather than being sent to the model at
all.
