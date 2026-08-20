# `utils/short_hash.py`

## module

`sha1(value)[:10]` - the one shared implementation behind every
`<hash>`-suffixed ID this pipeline mints (`SCR-`, `REQ-`, `EP-`, `MOD-`,
`CH-`, `MSG-`, `TERM-`, and `tree.aria.yaml`'s `template_hash`), pinned
by docs/adr/0015-master-llms-txt-manifest-contract.md, matching the
algorithm `spiders/content/component_matching.py` already used for this
exact purpose before this module existed to name it once. Never
reimplemented per document.

Callers own how their own identity-defining parts are normalized and
joined before calling this (e.g. `short_hash(f"{method} {host}{path}")`
for an `EP-<hash>`) - `short_hash` itself stays a pure hash, not a hidden
formatting rule.
