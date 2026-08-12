"""Plugin registries: the backbone of the micro-kernel."""
from __future__ import annotations

from typing import Any, Callable, Dict, Generic, List, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Maps plugin names to factory callables (classes or builder functions)."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._factories: Dict[str, Callable[..., T]] = {}

    def register(self, name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator: @REGISTRY.register("name") on a class or builder function."""
        def decorator(factory: Callable[..., T]) -> Callable[..., T]:
            self._factories[name.lower()] = factory
            return factory
        return decorator

    def create(self, name: str, **kwargs: Any) -> T:
        key = (name or "").lower()
        if key not in self._factories:
            available = ", ".join(sorted(self._factories)) or "(none registered)"
            raise KeyError(f"Unknown {self.kind} '{name}'. Available: {available}")
        return self._factories[key](**kwargs)

    def names(self) -> List[str]:
        return sorted(self._factories)


AGENT_REGISTRY: "Registry[Any]" = Registry("agent")
GRAPH_STORE_REGISTRY: "Registry[Any]" = Registry("graph_store")
# Output documents, resolved by name from PragmaConfig.documents. Unlike
# the two above, every factory here takes no arguments - a generator reads
# what it needs from the DocumentRequest it is handed at generate() time.
DOCUMENT_REGISTRY: "Registry[Any]" = Registry("document")
