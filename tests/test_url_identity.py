"""Tests for Fase 1: URL identity normalization - dynamic path segments (e.g. a
per-visit order/session token embedded in the path) and query-string policy, both
applied inside SimplePRDGenerator._clean_url before a URL becomes a graph-node key."""
from src.generators.prd_generator import SimplePRDGenerator
from tests.test_imports import ScriptedAgent, StubScraper


def _gen(tmp_path, **kwargs) -> SimplePRDGenerator:
    return SimplePRDGenerator(
        ScriptedAgent([]), StubScraper(), progress_file=str(tmp_path / "p.md"), **kwargs
    )


def test_clean_url_unchanged_by_default_no_config(tmp_path):
    """Regression guard: with no dynamic_url_segments configured, path segments
    must pass through exactly as before this feature existed."""
    gen = _gen(tmp_path)
    assert gen._clean_url("https://empanad.app/o/elk5kvp8trn54Kx2bNOlw0c3GjVCAGhhP") == (
        "empanad.app/o/elk5kvp8trn54Kx2bNOlw0c3GjVCAGhhP"
    )


def test_dynamic_segments_collapse_distinct_tokens_into_one_node(tmp_path):
    """The concrete bug this fixes: three order URLs that differ only by a
    per-visit token must normalize to the exact same graph-node key."""
    gen = _gen(tmp_path, dynamic_url_segments=[r"^[A-Za-z0-9]{16,}$"])

    keys = {
        gen._clean_url(u)
        for u in (
            "https://empanad.app/o/elk5kvp8trn54Kx2bNOlw0c3GjVCAGhhP",
            "https://empanad.app/o/9zQwT2xrLk0pAvBnMcYh1sDf3eKu",
            "https://empanad.app/o/aB7cD9eFgH2iJkL4mNoP6qRsT8uV",
        )
    }
    assert keys == {"empanad.app/o/{id}"}


def test_dynamic_segments_never_match_the_domain_segment(tmp_path):
    """A greedy/broad pattern must not be able to collapse the domain itself -
    only path segments after it are candidates."""
    gen = _gen(tmp_path, dynamic_url_segments=[r"^[A-Za-z0-9.]{5,}$"])
    assert gen._clean_url("https://short.io/AbCdEfGhIjKlMnOp") == "short.io/{id}"


def test_dynamic_segments_leave_non_matching_segments_alone(tmp_path):
    """A real, meaningful path segment (e.g. 'about', or a short product slug)
    that doesn't match the configured pattern must stay exactly as-is - this is
    what keeps normal navigation/pending-route tracking working unchanged."""
    gen = _gen(tmp_path, dynamic_url_segments=[r"^[A-Za-z0-9]{16,}$"])
    assert gen._clean_url("https://empanad.app/menu") == "empanad.app/menu"
    assert gen._clean_url("https://empanad.app/o/short") == "empanad.app/o/short"


def test_strip_query_params_defaults_to_dropping_everything(tmp_path):
    gen = _gen(tmp_path)
    assert gen._clean_url("https://a.com/page?utm_source=ads&session=xyz") == "a.com/page"


def test_keep_query_params_whitelist(tmp_path):
    gen = _gen(tmp_path, keep_query_params=["page"])
    assert gen._clean_url("https://a.com/list?page=2&utm_source=ads") == "a.com/list?page=2"
    # No whitelisted param present -> nothing kept, same as full stripping.
    assert gen._clean_url("https://a.com/list?utm_source=ads") == "a.com/list"


def test_strip_query_params_false_preserves_query_untouched(tmp_path):
    gen = _gen(tmp_path, strip_query_params=False)
    assert gen._clean_url("https://a.com/page?foo=bar&baz=qux") == "a.com/page?foo=bar&baz=qux"


def test_resolve_goto_url_uses_first_sample_for_a_templated_key(tmp_path):
    """A Pending route the model picks might be a templated key (`domain/o/{id}`),
    which is not itself a loadable URL - navigating to it must resolve to a real,
    previously-seen concrete instance instead of the literal placeholder string."""
    gen = _gen(tmp_path, dynamic_url_segments=[r"^[A-Za-z0-9]{16,}$"])
    cleaned = gen._clean_url("https://empanad.app/o/elk5kvp8trn54Kx2bNOlw0c3GjVCAGhhP")
    assert cleaned == "empanad.app/o/{id}"

    resolved = gen._resolve_goto_url(cleaned)
    assert resolved == "https://empanad.app/o/elk5kvp8trn54Kx2bNOlw0c3GjVCAGhhP"

    # A second, different token for the same template must not overwrite the
    # first sample - the first real URL seen keeps being the one resolved to.
    gen._clean_url("https://empanad.app/o/9zQwT2xrLk0pAvBnMcYh1sDf3eKu")
    assert gen._resolve_goto_url(cleaned) == "https://empanad.app/o/elk5kvp8trn54Kx2bNOlw0c3GjVCAGhhP"


def test_discovered_links_with_distinct_tokens_are_tracked_as_one_pending_route(tmp_path):
    """End-to-end through _update_discovered_routes: three links to what a human
    would call "the same kind of page" (only the order token differs) must
    produce exactly one Pending route, not three separate ones."""
    gen = _gen(tmp_path, dynamic_url_segments=[r"^[A-Za-z0-9]{16,}$"])
    gen.base_domain = "empanad.app"

    gen._update_discovered_routes(
        [
            {"href": "https://empanad.app/o/elk5kvp8trn54Kx2bNOlw0c3GjVCAGhhP", "text": "Ver pedido"},
            {"href": "https://empanad.app/o/9zQwT2xrLk0pAvBnMcYh1sDf3eKu", "text": "Ver pedido"},
            {"href": "https://empanad.app/o/aB7cD9eFgH2iJkL4mNoP6qRsT8uV", "text": "Ver pedido"},
        ],
        source="empanad.app/carrito",
    )

    assert gen.graph_store.get_pending("empanad.app") == ["empanad.app/o/{id}"]
