# `src/agents/local_agent.py`

## LocalConfig

This is the single place that knows about
`LOCAL_API_URL`/`LOCAL_MODEL`/`LOCAL_API_KEY`/`LOCAL_MAX_TOKENS` - no
other module should read those env vars directly.

## max_tokens

Unset by default (unlike `OpenAIAgent`'s hardcoded `max_tokens=1200`) -
a local reasoning model (DeepSeek-R1 and similar) can legitimately need
many tokens of chain-of-thought before it reaches its actual answer,
and guessing a "safe" default risks silently truncating that
mid-thought. Opt in explicitly once you know your model's real budget.

## LocalAgent

Post-crawl4ai-migration: this is plain text-completion only - the
native OpenAI-style tool-calling ladder (`act()`/`_act_native`/
`_parse_tool_call`) that used to live here existed solely to fill a
per-step structured action schema, which no longer exists (see
`src/core/interfaces.py`'s module doc). `generate()` is used by the
fill-value (Phase 4) and synthesis (Phase 5) call sites, both plain
text completions.

## _raise_if_truncated

Raise a clear, actionable error if the server cut the response off for
running out of `max_tokens`, rather than let it masquerade as something
else downstream.

`finish_reason == "length"` is the OpenAI-compatible signal for this -
present regardless of whether the server separates a reasoning model's
chain-of-thought into its own `reasoning_content` field or leaves it
inline in `content`. Without this check, a reasoning model (DeepSeek-R1
and similar) that spends its entire `max_tokens` budget "thinking"
returns an empty `content` - which looks, from every other code path's
point of view, like an ordinary malformed response, silently giving no
indication the actual cause was one fixed, config-level number.
