# Startup

```bash
docker compose up -d neo4j       # graph store (skip if graph_store: memory in pragma.yaml)
python -m src.api_server         # only if scraper: rest in pragma.yaml
python3 src/cli.py https://example.com
```
