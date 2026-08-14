"""Regression tests for utils/urls.py's canonicalization functions."""
from utils.urls import clean_url, is_in_scope, route_shape


def test_clean_url_strips_scheme_trailing_slash_and_fragment():
    assert clean_url("https://example.com/x/#section") == "example.com/x"
    assert clean_url("http://example.com/x") == "example.com/x"


def test_clean_url_strips_www():
    """Confirmed live on empanad.app (see debug_logs/): the crawler tracked
    `https://empanad.app` and `https://www.empanad.app/` as two distinct
    frontier/session keys, each independently re-triggering the site's
    per-visit redirect - www vs. bare must collapse to one identity."""
    assert clean_url("https://www.empanad.app") == clean_url("https://empanad.app")
    assert clean_url("https://www.example.com/x") == "example.com/x"


def test_route_shape_collapses_token_segments_but_not_real_slugs():
    """A per-visit token path (empanad.app's actual `/o/<hash>` shape)
    collapses to a shared route shape across different real hashes, while a
    human-authored slug keeps its own identity - the whole point of
    route_shape() being a *separate*, coarser key than clean_url()."""
    a = route_shape("https://www.empanad.app/o/IJ_zXcXRtxGTl1_lxD-eR6BIcYJwLglV")
    b = route_shape("https://empanad.app/o/HilNN6lA9xYMONnszrDuwxe2xIRbuzEM")
    assert a == b

    # clean_url() must still keep them as distinct real identities - route_shape
    # is a dedup/bounding key only, never a replacement for node identity.
    assert clean_url("https://www.empanad.app/o/IJ_zXcXRtxGTl1_lxD-eR6BIcYJwLglV") != clean_url(
        "https://empanad.app/o/HilNN6lA9xYMONnszrDuwxe2xIRbuzEM"
    )

    assert route_shape("https://example.com/admisiones") == route_shape("https://example.com/admisiones")
    assert route_shape("https://example.com/admisiones") != route_shape("https://example.com/about-us")


def test_route_shape_never_collapses_short_or_short_slugs():
    """A short path segment (well under the opaque-token length threshold)
    is never mistaken for a generated token, even if it happens to mix case
    or contain digits (e.g. a product id like "sku42")."""
    assert route_shape("https://example.com/sku42") == "example.com/sku42"


def test_is_in_scope_same_host_regardless_of_scheme_www_or_path():
    assert is_in_scope("https://example.com/about", "https://example.com")
    assert is_in_scope("http://www.example.com/x", "https://example.com/")


def test_is_in_scope_rejects_different_host_by_default():
    assert not is_in_scope("https://evil.com/", "https://example.com")
    assert not is_in_scope("https://example.com.evil.com/", "https://example.com")


def test_is_in_scope_subdomain_needs_allow_subdomains():
    assert not is_in_scope("https://blog.example.com/", "https://example.com")
    assert is_in_scope("https://blog.example.com/", "https://example.com", allow_subdomains=True)
    # A sibling subdomain of the base's own subdomain also passes, via the
    # shared last-two-labels - the documented naive-PSL tradeoff, not a bug.
    assert is_in_scope("https://shop.example.com/", "https://blog.example.com", allow_subdomains=True)


def test_is_in_scope_fails_open_on_empty_host():
    """A backstop check, not the primary identity check - a weak/absent
    signal (no host to compare at all) must never itself block a crawl that
    would otherwise proceed."""
    assert is_in_scope("", "https://example.com")
    assert is_in_scope("https://example.com", "")
