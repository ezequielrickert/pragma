"""URL canonicalization - the one function every URL used as a graph/dedup key must go through.
Details: docs/dev/utils/urls.md#module
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

# An opaque, per-visit token path segment (session id, order hash, nonce).
# Details: docs/dev/utils/urls.md#_token_segment_re
_TOKEN_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_-]{16,}$")


def _looks_generated(segment: str) -> bool:
    """True if `segment` mixes digits/letter-cases the way a generated token does.
    Details: docs/dev/utils/urls.md#_looks_generated
    """
    has_digit = has_lower = has_upper = False
    for ch in segment:
        if ch.isdigit():
            has_digit = True
        elif ch.islower():
            has_lower = True
        elif ch.isupper():
            has_upper = True
    return has_digit or (has_lower and has_upper)


def is_opaque_token(segment: str) -> bool:
    """Public wrapper combining `_TOKEN_SEGMENT_RE` + `_looks_generated` -
    `route_shape`'s own per-path-segment check, exposed for any other
    code that needs the identical "does this look like a generated id,
    not a real word" judgment on a single path segment.
    `database/ladybug/network.py::_pattern_and_params` is the other
    caller (an API URL's dynamic `/orders/<uuid>/` segment is the same
    kind of per-instance noise a page's own session token is - same
    heuristic, different URL kind).
    Details: docs/dev/utils/urls.md#is_opaque_token
    """
    return bool(_TOKEN_SEGMENT_RE.match(segment)) and _looks_generated(segment)


def clean_url(url: str) -> str:
    """Canonicalize `url` into a stable dedup/graph-node key.
    Details: docs/dev/utils/urls.md#clean_url
    """
    cleaned = url.split("#")[0].rstrip("/")
    for prefix in ("https://", "http://"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    if cleaned.startswith("www."):
        cleaned = cleaned[len("www."):]
    return cleaned


def route_shape(url: str) -> str:
    """Collapse any opaque per-visit-token path segment into a shared `{token}`.
    Details: docs/dev/utils/urls.md#route_shape
    """
    cleaned = clean_url(url)
    host, _, path = cleaned.partition("/")
    if not path:
        return cleaned
    segments = path.split("/")
    shaped = [
        "{token}" if is_opaque_token(seg) else seg
        for seg in segments
    ]
    return host + "/" + "/".join(shaped)


def _host(url: str) -> str:
    """`clean_url()`'s own host-extraction step, standalone."""
    return clean_url(url).partition("/")[0]


def slugify(url: str) -> str:
    """Turn `url` into a filesystem-safe slug - the one function every
    per-site filename (a debug-log run directory, a generated document, a
    `.lbdb` database file) derives its name from, so the same URL always
    resolves to the same path.
    Details: docs/dev/utils/urls.md#slugify
    """
    return url.replace("https://", "").replace("http://", "").replace("/", "_")


def resolve_href(base_url: str, href: str) -> Optional[str]:
    """Resolve a possibly-relative anchor `href` (the raw DOM attribute -
    discover_components.js's own `getAttribute('href')`, not the
    browser-resolved `.href` property) against `base_url` into an
    absolute, navigable URL - or `None` if `href` isn't one: empty, a
    same-page fragment (`#section`), or a non-http(s) pseudo-scheme
    (`javascript:`, `mailto:`, `tel:`).

    The eager pre-click check `PageVisitor.visit()` uses: a real `<a
    href>` component's destination is knowable without ever clicking it,
    so a known destination never has to cost a browser navigation at all.
    Details: docs/dev/utils/urls.md#resolve_href
    """
    href = (href or "").strip()
    if not href or href.startswith("#"):
        return None
    resolved = urljoin(base_url, href)
    if urlparse(resolved).scheme.lower() not in ("http", "https"):
        return None
    return resolved


def is_in_scope(url: str, base_url: str, allow_subdomains: bool = False) -> bool:
    """Whether `url` belongs to the same site as `base_url` (host-only comparison).
    Details: docs/dev/utils/urls.md#is_in_scope
    """
    target = _host(url)
    base = _host(base_url)
    if not target or not base:
        return True
    if target == base:
        return True
    if not allow_subdomains:
        return False
    target_labels = target.split(".")
    base_labels = base.split(".")
    if len(target_labels) < 2 or len(base_labels) < 2:
        return False
    return target_labels[-2:] == base_labels[-2:]
