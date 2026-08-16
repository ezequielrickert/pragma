"""Guards a real bug found while splitting core/interfaces.py's GraphStore
into topic-split mixin files (Storage Phase 6): a plain mixin class (not
itself subclassing ABC) whose methods carry @abstractmethod is silently
UNENFORCED once composed into an ABC subclass - Python's ABCMeta only
collects a composed class's __abstractmethods__ by reading each base's own
__abstractmethods__ attribute, which only exists on classes that
themselves went through ABCMeta.__new__. A backend missing a whole mixin's
worth of methods would still instantiate, failing only with
NotImplementedError the first time one of those specific methods was
actually called - not at construction time, where every other missing
method already fails loudly.

This file has one job: prove GraphStore still rejects an incomplete
subclass covering every mixin's worth of methods, so a future refactor
that drops `(ABC)` from one of the split interface files (an easy,
plausible-looking "simplification") gets caught immediately instead of
degrading into a silent, lazy failure discovered much later.
"""
import pytest

from core.interfaces import GraphStore


def test_graph_store_rejects_a_subclass_missing_every_abstract_method():
    class Empty(GraphStore):
        pass

    with pytest.raises(TypeError, match="abstract"):
        Empty()


def test_graph_store_abstract_methods_cover_every_split_interface_file():
    """Each split-out interface file (_component_store_interface.py,
    _component_family_interface.py, _request_family_interface.py,
    _text_content_interface.py, _page_extras_interface.py) contributes at
    least one abstract method GraphStore still enforces - if any one of
    them lost its `(ABC)` base, its methods would silently vanish from
    this set instead of raising here.
    """
    abstracts = GraphStore.__abstractmethods__
    # One representative abstract method per split file - not exhaustive,
    # just enough to prove each file's mixin is still contributing.
    representative_methods = {
        "record_component",  # _component_store_interface.py
        "record_component_families",  # _component_family_interface.py
        "record_inferred_requests",  # _request_family_interface.py
        "record_text_content",  # _text_content_interface.py
        "record_page_network",  # _page_extras_interface.py
        "upsert_page",  # interfaces.py's own core Page/Site/edge methods
    }
    missing = representative_methods - abstracts
    assert not missing, f"these abstract methods vanished from GraphStore: {missing}"


def test_a_backend_implementing_only_some_mixins_is_still_rejected():
    """Not just "zero methods implemented" (the first test) - a subclass
    that fully satisfies one mixin but skips another must still fail,
    proving the union really is enforced, not just the first base checked.
    """
    class PartiallyComplete(GraphStore):
        # Satisfies every abstract method interfaces.py declares directly...
        def connect(self): pass
        def close(self): pass
        def upsert_page(self, site, url, **kwargs): pass
        def get_page_descriptions(self, site): return {}
        def get_page_titles(self, site): return {}
        def is_visited(self, site, url): return False
        def get_pending(self, site, limit=None): return []
        def get_page_label(self, site, url): return None
        def record_link(self, site, from_url, to_url, label): pass
        def get_link_label(self, site, from_url, to_url): return None
        def record_edge(self, site, from_url, to_url, component, action, run_id=""): pass
        def get_edges(self, site): return []
        def get_progress_table_rows(self, site): return []
        def count_visited(self, site): return (0, 0)
        def get_loop_signals(self, site, url): return []
        def clear_site(self, site): pass
        # ...but never touches _ComponentStoreInterface's methods at all.

    with pytest.raises(TypeError, match="record_component"):
        PartiallyComplete()
