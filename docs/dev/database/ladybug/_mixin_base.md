# database/ladybug/_mixin_base.py

## module

Shared typing contract for every `_Ladybug*Mixin` in this package, added
when the codebase adopted mypy strict mode (issue #250). Each mixin's own
docstring already documented that it "relies on `self._call(...)` existing
on whatever it ends up mixed into" - true at runtime because
`store.py::LadybugGraphStore` combines all seventeen mixins via multiple
inheritance, but invisible to mypy, which type-checks each mixin file in
isolation and has no way to know the cross-mixin contract holds.

Every mixin now inherits from `_LadybugMixinBase` instead of `object`, so
mypy resolves `self._call(...)`, `self._ensure_page(...)` and
`self.get_pending(...)` the same way the real MRO does at runtime. The
methods here are stub signatures only, never called directly -
`page.py`/`store.py` supply the real bodies that `LadybugGraphStore`'s MRO
picks up.

## _ladybugmixinbase

One class, three stub methods, matching the three cross-mixin calls that
existed when this file was added. A future mixin that needs a fourth
should add its stub here rather than reaching for a per-call-site
`# type: ignore`.
