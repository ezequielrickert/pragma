"""Module 3: unified local REST API - execution (`/dynamic`) + curated docs (`/static`).

Thinking of the system as three modules (see ARCHITECTURE.md's "Module 3: Unified REST API"):
Module 1 is the remote LM Studio/model server (Tailscale-tunneled, portable to any
OpenAI-compatible API); Module 2 is the orchestrator (`SimplePRDGenerator`/`Engine`, this Mac);
Module 3 is this package - a standing local service the orchestrator talks to over plain HTTP.

The model never calls this API directly - it only ever picks a short verb from `TOOL_SPECS`
(`src/core/interfaces.py`); the orchestrator is what parses that choice and makes the HTTP call
here on the model's behalf.
"""
