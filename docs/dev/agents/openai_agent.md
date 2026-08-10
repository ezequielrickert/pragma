# `src/agents/openai_agent.py`

## OpenAIConfig

This is the single place that knows about
`OPENAI_API_KEY`/`OPENAI_MODEL` - no other module should read those env
vars directly.

## OpenAIAgent

Ported from the pre-1.0 `openai.ChatCompletion.create(...)` module-level
call style during the crawl4ai migration - installing crawl4ai
transitively upgraded the `openai` package (1.0.0 -> 2.53.0+ in this
venv), which removed `openai.ChatCompletion`/module-level
`openai.api_key` entirely. Not a design change, just following the
SDK's own client-instance model.
