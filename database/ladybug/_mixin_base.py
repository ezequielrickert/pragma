"""Shared typing contract for every `_Ladybug*Mixin` in this package.

Each mixin's own docstring already documents that it "relies on
`self._call(...)` existing on whatever it ends up mixed into" - true at
runtime because `store.py::LadybugGraphStore` combines all of them via
multiple inheritance, but invisible to mypy, which sees each mixin in
isolation and has no way to know the cross-mixin contract holds. Every
mixin inherits from `_LadybugMixinBase` instead of `object` so mypy can
resolve `self._call(...)`, `self._ensure_page(...)` and
`self.get_pending(...)` the same way the real MRO does - stub signatures
only, never called directly; `page.py`/`store.py` supply the real bodies.

Details: docs/dev/database/ladybug/_mixin_base.md#module
"""
from __future__ import annotations

from typing import Callable, List, Optional, TypeVar

import ladybug as lb

_T = TypeVar("_T")


class _LadybugMixinBase:
    """Stub signatures for the methods every `_Ladybug*Mixin` calls on
    `self` but does not itself define - resolved for real through
    `LadybugGraphStore`'s MRO (`store.py::_call`, `page.py::_ensure_page`/
    `get_pending`).
    Details: docs/dev/database/ladybug/_mixin_base.md#_ladybugmixinbase
    """

    def _call(self, fn: Callable[[lb.Connection], _T]) -> _T:
        raise NotImplementedError

    def _ensure_page(self, conn: lb.Connection, url: str) -> None:
        raise NotImplementedError

    def get_pending(self, limit: Optional[int] = None) -> List[str]:
        raise NotImplementedError
