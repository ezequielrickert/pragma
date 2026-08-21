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
    # The raw `DocumentOutput.filename` this was built from (e.g.
    # `"architecture.calm"`) - `path` is `DocumentNaming.path_for`'s
    # timestamped, slug-prefixed disk path, which a reader can't reliably
    # reverse back into this stable identifier (the slug and the
    # filename can both contain `_`/`.`). `manifest.json`/`llms.txt`
    # (docs/adr/0015) key their own lookups on this, not on `path`.
    # Details: docs/dev/core/documents.md#produceddocumentfilename
    filename: str = ""
    # `path`, relative to the run's own `out_dir` - what a link inside
    # another document this same run writes (`master.md`, `llms.txt`)
    # must point at. Equal to `Path(path).name` for every flat document
    # (the common case, unchanged), but a nested one (`decisions.adr/`'s
    # own numbered files, ADR-0023) lives inside a subdirectory `path`'s
    # bare basename would silently drop - computed once in
    # `generators/pipeline.py::_write_document`, the one place that has
    # both `path` and `out_dir` in scope together.
    # Details: docs/dev/core/documents.md#produceddocumentrelative_link
    relative_link: str = ""


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
    # `generators.coverage.CrawlCoverage`, computed once per run by
    # `run_document_pipeline` and shared by every generator - typed loosely
    # here, same as `graph_store`, so this module (the abstract contract
    # every generator builds on) never has to import from `generators/`.
    # `coverage`'s own generator reads this instead of a second live query;
    # every Markdown document's banner reads it instead of a live query per
    # document, which is what "computed once per run" (docs/adr/0001)
    # actually requires.
    coverage: Any = None


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
