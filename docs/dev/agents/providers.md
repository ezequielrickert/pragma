# `src/agents/providers.py`

## module

Each provider owns its config (a dataclass colocated with its Agent
implementation, e.g. `GeminiConfig` in `gemini_agent.py`). These
builders only decide *which* concrete class to instantiate and forward
any explicit overrides (e.g. from `pragma.yaml`'s `agents:` block) on
top of that provider's own env-derived defaults.
