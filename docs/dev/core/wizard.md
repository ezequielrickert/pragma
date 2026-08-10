# `src/core/wizard.py`

## module

Non-secret settings (which plugins, model names, endpoints) are written
to `pragma.yaml`. Secrets (API keys) are written to `.env`. Existing
values are shown as editable defaults, so re-running the wizard is a
safe way to tweak a single setting without hand-editing YAML.

## _prompt_provider_fields

Generic over any per-provider fields table shaped like `PROVIDER_FIELDS`
- reused for `GRAPH_STORE_FIELDS` so agent and graph-store setup share
one prompt/persist implementation instead of duplicating the
secret/non-secret branching logic.
