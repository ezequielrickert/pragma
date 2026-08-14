"""Public surface of the mechanical_loop package - re-exported so every
existing `from spiders.orchestration.mechanical_loop import
MechanicalCrawler` (and `MechanicalCrawlerConfig`) elsewhere in the
codebase keeps working unchanged.
"""
from .config import MechanicalCrawlerConfig
from .loop import MechanicalCrawler

__all__ = ["MechanicalCrawler", "MechanicalCrawlerConfig"]
