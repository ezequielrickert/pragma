# Global chat routes to documents before grounding, never widens blindly

**Status**: accepted

[Persistent global chat](https://github.com/ezequielrickert/pragma/issues/180) must answer a question
grounded in whichever document actually holds the answer, not just whichever page happens to be
open. ADR-0032's tiered grounding and ADR-0033 point 4 both assume a single `DocumentRef` per turn
(`grounding_for(where, ref)` + `system_instruction_for(ref, facts)` on the document currently being
edited). Checked whether that model could simply drop the `ref` filter and aggregate every
document's facts instead:

- **Blind widening fails the bar.** Dumping every handler in `_GROUNDING_BY_FILENAME` into one
  prompt on every turn would mix unrelated facts (token citers beside risk-register services beside
  content-inventory copy), blow context on a full 22-document site, and give the model no signal
  about *which* document a cited fact belongs to when it replies with a link rather than navigating
  there (map #172's own requirement).
- **A second LLM call just to pick a document fails the bar for v1.** Adds latency and a new failure
  mode (the router hallucinates a document name with no grounding loaded for it) before the chat has
  even tried to answer - solved speculatively for a problem the deterministic path hasn't hit yet,
  the same bias ADR-0033 took against capping history early.
- **Keyword routing against produced files is real today.** `interactive/customization.py::
  available_documents()` already lists every distinct `(filename, extension)` on disk;
  `dashboard/document_context.py` already carries a plain-language explanation per registry name the
  router can tokenize - no new index, no live graph-store connection.

Decided:

**1. Route, then ground - two explicit steps per turn.** `select_grounding_documents(where,
message, context_ref=...)` returns up to three `DocumentRef`s; `grounding_for_documents(where,
refs)` calls the existing per-document handlers and returns `SourcedGroundingFact(source, statement)`
rows so every fact names the document it came from. The global chat never calls `grounding_for`
with "whatever page is open" as the only scope.

**2. Routing is deterministic in v1 - no extra model call.** Score each produced document by token
overlap between the user's message and routing tokens derived from `(filename, registry alias,
document_context explanation)`. Always include `context_ref` when the UI has one (the document
currently open in the content panel) as a hint, not an exclusive lock - a user viewing `tokens.json`
who asks about risks still gets `risk-register` when the message matches it. Cap at three
documents; when nothing scores, return only the context hint or an empty list (tier C for that
turn), never fall back to "all documents with a handler."

**3. Registry aliases are explicit, not inferred.** Filenames like `custom-elements.json` map to
`catalog` for `document_context` lookup the same way `dashboard/renderer_audit.py` already treats
catalog as the human-facing name - the router carries a small alias table rather than guessing.

**4. Global chat gets its own standing instruction template.** `system_instruction_for_global(refs,
facts)` replaces the edit-oriented "help someone edit {filename}" header with Q&A guidance: cite
only listed facts; when a fact's source document is relevant to the answer, name it and give the
real path `/document/{filename}.{extension}`; never auto-navigate the browser there (map #172). Per-
document edit chat on `/edit` keeps `system_instruction_for` unchanged.

**Consequence**: ticket #180 wires the persistent panel to session-scoped history, calls
`select_grounding_documents` + `grounding_for_documents` + `system_instruction_for_global` each turn,
and renders document links inline. Extending tier-a/b coverage to more document types (ADR-0032's own
"real future work") stays per-handler work inside `grounding_for` - the global router doesn't change
when a new handler lands.
