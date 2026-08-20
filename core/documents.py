"""Contracts for the document pipeline: what a generator is, what it gets,
and what it produces.

Lives in its own module rather than in `interfaces.py` for the same reason
`data_contracts.py` does - `interfaces.py` holds the *crawl's* own
contract (`Agent`), and the document pipeline is a separate concern that
happens to consume it. Keeping it here also stops `interfaces.py` from
drifting further past this project's file-size threshold.

Details: docs/dev/core/documents.md#module
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, Literal, Tuple, Union

from .interfaces import Agent

# The taxonomy CONTEXT.md's glossary defines for the doc-generation pipeline:
# a source document is machine-checkable ground truth; a view is rendered
# from one for a human reader; a projection reshapes pragma's own data (the
# graph, or another document) into an external standard's schema; a rule
# catalog is fixed to a rule-set version rather than derived from a crawl.
DocumentKind = Literal["source", "view", "projection", "rule-catalog"]


@dataclass(frozen=True)
class DocumentOutput:
    """One physical file a `DocumentGenerator` produces.

    `filename` is the stem only, no extension - `DocumentNaming.path_for`
    (generators/pipeline.py) appends the run's slug/timestamp wrapper and
    `extension` itself, the same way it already names every document today.
    Details: docs/dev/core/documents.md#documentoutput
    """

    filename: str
    kind: DocumentKind
    extension: str
    content: str


@dataclass(frozen=True)
class ProducedDocument:
    """One document a finished pipeline run wrote to disk.
    Details: docs/dev/core/documents.md#produceddocument
    """

    name: str
    title: str
    purpose: str
    path: str
    kind: DocumentKind = "view"
    checksum: str = ""


@dataclass(frozen=True)
class DocumentRequest:
    """Everything a generator is allowed to read.
    Details: docs/dev/core/documents.md#documentrequest
    """

    graph_store: Any
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
    def generate(self, request: DocumentRequest) -> Union[str, Tuple[DocumentOutput, ...]]:
        """Return this document's content. Never writes to disk itself.

        A generator producing exactly one file returns a plain `str` - the
        original contract, still fully supported unchanged. `outputs()`
        wraps it into a single `DocumentOutput` automatically, so a
        single-file generator needs no changes to keep working. A generator
        producing several files (a source/view split, or more) returns a
        tuple of `DocumentOutput` directly, owning each file's own
        `filename`/`kind`.
        Details: docs/dev/core/documents.md#generate
        """
        raise NotImplementedError

    def outputs(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        """Normalize `generate()`'s result to the multi-file shape every
        caller actually wants - the one place this wrapping happens, so
        `generate()`'s two accepted return shapes never leak past here.
        Details: docs/dev/core/documents.md#outputs
        """
        result = self.generate(request)
        if isinstance(result, str):
            return (DocumentOutput(filename=self.name, kind="view", extension=self.extension, content=result),)
        return result
