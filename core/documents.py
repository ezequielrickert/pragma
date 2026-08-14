"""Contracts for the document pipeline: what a generator is, what it gets,
and what it produces.

Lives in its own module rather than in `interfaces.py` for the same reason
`data_contracts.py` does - `interfaces.py` holds the *crawl's* contracts
(`Agent`, `GraphStore`), and the document pipeline is a separate concern
that happens to consume them. Keeping it here also stops `interfaces.py`
from drifting further past this project's file-size threshold.

Details: docs/dev/core/documents.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Tuple

from .interfaces import Agent, GraphStore


@dataclass(frozen=True)
class ProducedDocument:
    """One document a finished pipeline run wrote to disk.
    Details: docs/dev/core/documents.md#produceddocument
    """

    name: str
    title: str
    purpose: str
    path: str


@dataclass(frozen=True)
class DocumentRequest:
    """Everything a generator is allowed to read.
    Details: docs/dev/core/documents.md#documentrequest
    """

    graph_store: GraphStore
    site: str
    agent: Agent
    settings: Dict[str, Any] = field(default_factory=dict)
    # Empty for every ordinary generator; filled only for the master
    # document, which runs last and describes what the others produced.
    # Details: docs/dev/core/documents.md#documentrequestproduced
    produced: Tuple[ProducedDocument, ...] = ()


class DocumentGenerator(ABC):
    """One output document: what it's called, what it's for, how to build it.

    Subclasses declare their identity as class attributes and implement
    `generate`. They take no constructor arguments - everything they need
    arrives in the `DocumentRequest`, which is what lets
    `DOCUMENT_REGISTRY.create(name)` build any of them without the caller
    knowing which one it asked for.

    Attributes:
        name: registry key, config name, and manifest key - one string
            serving all three so a document can't be called three things
            (e.g. `"prd"`).
        title: human heading, used in the master document and the docs
            index (e.g. `"Digital Blueprint"`).
        purpose: one sentence on what this document is for, shown in the
            master document so a reader knows which file to open. Written
            once here rather than restated per consumer.
        extension: file extension without the dot; `"md"` unless the
            document is something else (`"json"`, `"yaml"`).
    Details: docs/dev/core/documents.md#documentgenerator
    """

    name: ClassVar[str] = ""
    title: ClassVar[str] = ""
    purpose: ClassVar[str] = ""
    extension: ClassVar[str] = "md"

    @abstractmethod
    def generate(self, request: DocumentRequest) -> str:
        """Return this document's full text. Never writes to disk itself.
        Details: docs/dev/core/documents.md#generate
        """
        raise NotImplementedError
