"""Load .env once for the whole pytest session.

Only `cli.py` called `load_dotenv()` before this - any test touching a
provider that reads its config from env vars (e.g. the local agent's
`LOCAL_API_KEY`, or the now-retired Neo4j backend's `NEO4J_PASSWORD`,
back when this project still had one) had no way to pick up
`.env`-configured secrets unless they were also exported in the shell.
Found live via Neo4j's own collection-time reachability check connecting
with a missing password even when `.env` had one - the concrete incident
is gone with that backend, but the general lesson (config from env vars
needs `.env` loaded before test collection, not just before `cli.py`
runs) still applies to every remaining env-var-configured provider.
"""
from dotenv import load_dotenv

load_dotenv(override=True)

# Populate AGENT_REGISTRY/GRAPH_STORE_REGISTRY once for the whole pytest
# session - previously only cli.py did this import, so any test file
# that calls Engine.from_config()/AGENT_REGISTRY.create()/
# GRAPH_STORE_REGISTRY.create() directly (e.g. tests/test_graph_store.py)
# only worked by accident, when some other test file happened to be
# collected first and imported an agent/graph-store module as a side effect.
# Running that file in isolation (`pytest tests/test_graph_store.py`) failed
# with "Unknown agent 'mock'" - a real test-isolation bug, not a fixture
# quirk - found while auditing the storage layer for
# docs/explicativos/plan-almacenamiento.md. See core/bootstrap.py.
from core import bootstrap  # noqa: E402, F401
