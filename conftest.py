"""Load .env once for the whole pytest session.

Only `src/cli.py` called `load_dotenv()` before this - any test touching a
provider that reads its config from env vars (e.g. `Neo4jGraphStore`) had no
way to pick up `.env`-configured secrets like `NEO4J_PASSWORD` unless they
were also exported in the shell. In practice this meant every pytest run's
collection-time `_neo4j_reachable()` check in
tests/test_neo4j_graph_store_integration.py connected with a missing
password even when `.env` had one - triggering a real (if harmless) "missing
key `credentials`" WARN on the Neo4j server's own logs for a check most runs
never intended to actually exercise.
"""
from dotenv import load_dotenv

load_dotenv(override=True)

# Populate AGENT_REGISTRY/GRAPH_STORE_REGISTRY once for the whole pytest
# session - previously only src/cli.py did this import, so any test file
# that calls Engine.from_config()/AGENT_REGISTRY.create()/
# GRAPH_STORE_REGISTRY.create() directly (e.g. tests/test_graph_store.py)
# only worked by accident, when some other test file happened to be
# collected first and imported an agent/graph-store module as a side effect.
# Running that file in isolation (`pytest tests/test_graph_store.py`) failed
# with "Unknown agent 'mock'" - a real test-isolation bug, not a fixture
# quirk - found while auditing the storage layer for
# docs/explicativos/plan-almacenamiento.md. See src/core/bootstrap.py.
from src.core import bootstrap  # noqa: E402, F401
