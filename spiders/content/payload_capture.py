"""Shared truncate-and-hash primitive for anything stored content-addressed
(network bodies via `network_filter.py`, stylesheets via `GraphStoreSink`) -
one place computing "the excerpt actually stored, the original size, and
the hash it's keyed by" so the two capture paths can't drift on how a
payload becomes a `payloads`-table row.

Details: docs/dev/spiders/content/payload_capture.md#module
"""
from __future__ import annotations

import hashlib
from typing import Optional, Tuple


def truncate_and_hash(text: Optional[str], cap_bytes: int) -> Tuple[str, int, str]:
    """Truncate `text` for storage while keeping its real size and identity.

    Args:
        text: the content to store, already redacted if it needed to be -
            this function has no opinion on redaction, it only bounds size
            and computes identity.
        cap_bytes: the maximum UTF-8 byte length of the returned excerpt.

    Returns:
        `(excerpt, byte_length, sha256_hex)`. `byte_length` is `text`'s
        *original* UTF-8 byte length, so "this was huge" survives even
        when the excerpt doesn't. `sha256_hex` hashes the full `text`, not
        just the excerpt - two payloads identical for their first
        `cap_bytes` but different afterward must not collide as "the same
        payload" just because their stored excerpts would look alike.
        `("", 0, "")` for an empty/`None` `text`.
    """
    if not text:
        return "", 0, ""
    encoded = text.encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    excerpt = encoded[:cap_bytes].decode("utf-8", errors="ignore")
    return excerpt, len(encoded), digest
