# `src/agents/gemini_agent.py`

## GeminiConfig

This is the single place that knows about
`GEMINI_API_KEY`/`GEMINI_MODEL` - no other module should read those env
vars directly.
