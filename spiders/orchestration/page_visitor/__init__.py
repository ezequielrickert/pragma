"""Public surface of the page_visitor package - re-exported so every
existing `from spiders.orchestration.page_visitor import PageVisitor`
elsewhere in the codebase keeps working unchanged.
"""
from .visitor import PageVisitor

__all__ = ["PageVisitor"]
