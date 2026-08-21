# Multi-turn chat via a new `Agent.converse()`, `LocalAgent` building the real `messages` array

**Status**: accepted

`core/interfaces.py::Agent` is single-shot and stateless today - `generate(prompt,
system_instruction=None) -> str`, called once per document/page across every existing generator
(`graph_prd_synthesizer.py` and friends). [Interactive dashboard](https://github.com/ezequielrickert/pragma/issues/146)
needs a real conversation: the user's message, the model's reply, and prior turns all still
relevant to the next thing the user asks.

Checked `agents/local_agent.py::LocalAgent._build_payload` before designing this: it already talks
an OpenAI-compatible `/v1/chat/completions` endpoint with a real `messages` array (`[{"role":
"system", ...}, {"role": "user", ...}]`) - it just always builds exactly one system turn and one
user turn per call. The multi-turn transport already exists; only what goes into that array needs
to widen.

Decided:

**1. `Agent` gains a new concrete method, `converse()` - not a signature change to `generate()`.**
```python
def converse(self, messages: List[Dict[str, str]], system_instruction: Optional[str] = None) -> str:
    """Default: no real history - just the last user turn. Override for a
    real one."""
    last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
    return self.generate(last_user, system_instruction)
```
`messages` is `[{"role": "user"|"assistant", "content": str}, ...]` - the same shape
`_build_payload` already builds internally, just handed in as history instead of a single string.
The default implementation lives on the base `Agent` class and every existing subclass inherits it
unchanged - none of them need to know `converse()` exists, and every single-shot call site
(`generate()`) is untouched.

**2. `LocalAgent` overrides `converse()` to build the real, full `messages` array.** Prepend
`system_instruction` as a `system` turn, then every entry of `messages` as-is, then POST through
the same `_build_payload`/`_generate_request` machinery `generate()` already uses (widened to
accept a pre-built message list instead of always synthesizing a 1-2-turn one). This is the
transport `LocalAgent` was already speaking - no new HTTP shape, no new dependency.

**3. Full session history, no window or summary.** Every turn from the current in-memory chat
session (map #146's own "history is in-memory only" decision) rides in `messages`, uncapped -
consistent with this project's existing bias against artificial caps (`LOCAL_MAX_TOKENS` unset by
default, "let the model use as much as it needs" per `local_agent.py`'s own truncation-error
message). Revisit only once a real session shows this actually degrading latency or quality - not
solved speculatively for a problem not yet observed.

**4. `system_instruction` is rebuilt every turn, not fixed once per session.** It always carries
the same standing instruction (guide the user through a change; cite only facts the grounding
pipeline (ADR-0032) actually supplied; say plainly when no real dependency data exists for the
current edit - never invent a consequence), plus whatever ADR-0032's tiered grounding resolves for
*the document currently open in the editor* at the moment of that turn. Grounding is a property of
what's being edited right now, not of the conversation's own history, so it's recomputed per turn
rather than cached from an earlier one - the user can switch which document they're editing
mid-conversation.

**Consequence**: the interactive dashboard's own chat module holds the in-memory `List[Dict[str,
str]]` history and calls `agent.converse(history + [new_user_turn], system_instruction=...)` each
turn, appending both the user's message and the model's reply back into that same list afterward.
Building that module, the Flask route it lives behind, and the exact `system_instruction` template
text is separate implementation work this ADR doesn't itself specify.
