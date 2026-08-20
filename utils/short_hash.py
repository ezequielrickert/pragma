"""Deterministic short IDs for the doc-generation pipeline.

The one shared implementation behind every `<hash>`-suffixed ID this
pipeline mints (`SCR-`, `REQ-`, `EP-`, `MOD-`, `CH-`, `MSG-`, `TERM-`) -
pinned to `sha1(...)[:10]` by docs/adr/0015-master-llms-txt-manifest-contract.md,
matching the algorithm already used for this exact purpose in
spiders/content/component_matching.py. Never reimplemented per document.
Details: docs/dev/utils/short_hash.md#module
"""
from __future__ import annotations

import hashlib


def short_hash(value: str) -> str:
    """A deterministic 10-character hex ID from one identity-defining
    string. Callers own how their own parts are normalized and joined
    before calling this - e.g. `short_hash(f"{method} {host}{path}")` for
    `EP-<hash>` - so this stays a pure hash, not a hidden formatting rule.
    """
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
