"""Runs the configured document generators, then the master document.

This is what keeps `Engine` from growing a hardcoded block per output
file: adding a document is a new generator module plus a registry name in
config, and nothing here or in `Engine` changes.

Details: docs/dev/generators/pipeline.md#module
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import List, Sequence

from core.documents import DocumentGenerator, DocumentRequest, ProducedDocument
from core.registry import DOCUMENT_REGISTRY
from utils.io import write_output
from .coverage import build_coverage, render_coverage_banner
from .master_document import MasterDocument


@dataclass(frozen=True)
class DocumentNaming:
    """Where one run's documents go and how they are named.
    Details: docs/dev/generators/pipeline.md#documentnaming
    """

    out_dir: str
    slug: str
    timestamp: str

    def path_for(self, name: str, extension: str) -> str:
        """The one place output filenames are built, so every document is
        named the same way and the master document's relative links always
        resolve. Details: docs/dev/generators/pipeline.md#path_for
        """
        return f"{self.out_dir}/{self.slug}_{name}_{self.timestamp}.{extension}"


def _with_banner(content: str, generator: DocumentGenerator, request: DocumentRequest) -> str:
    """Prepend the coverage banner to Markdown documents only.

    Done here rather than in each generator so the rule lives in one place
    and a new document gets it by existing. Skipped for any other
    extension: a JSON or YAML file with a Markdown blockquote glued to the
    front is not a JSON or YAML file.
    Details: docs/dev/generators/pipeline.md#_with_banner
    """
    if generator.extension != "md":
        return content
    banner = render_coverage_banner(build_coverage(request.graph_store, request.site))
    return f"{banner}\n{content}"


def _write_document(generator: DocumentGenerator, request: DocumentRequest, path: str) -> ProducedDocument:
    """Build one document and write it. Raises whatever the generator
    raises - `run_document_pipeline` owns the decision to degrade rather
    than abort."""
    write_output(path, _with_banner(generator.generate(request), generator, request))
    return ProducedDocument(
        name=generator.name, title=generator.title, purpose=generator.purpose, path=path
    )


def run_document_pipeline(
    request: DocumentRequest, naming: DocumentNaming, names: Sequence[str]
) -> List[ProducedDocument]:
    """Generate every document in `names`, then the master document.

    Args:
        request: the base request handed to each generator. Its `produced`
            must be empty - this function fills it in for the master
            document's own request and for no one else.
        naming: where this run's files go and how they are named.
        names: registry names of the documents to generate, in order.

    Returns:
        One `ProducedDocument` per document actually written, master
        document last. A generator that fails is logged and skipped, not
        raised - the same "degrade this one output, don't abort the run"
        discipline `GraphPRDSynthesizer` already applies per page. A
        document that failed is absent from the list, so the master
        document never links to a file that isn't there.
    Details: docs/dev/generators/pipeline.md#run_document_pipeline
    """
    # Announced per document, not just as a batch: generator cost is wildly
    # uneven - most are deterministic and instant, while "prd" and "gherkin"
    # each make a model call per page/scenario. A single "generating N
    # documents" line would hide an hour inside one of them.
    # Details: research/plan-progreso-en-terminal.md
    print(f"\nGenerating {len(names)} documents, then the master document...")
    produced: List[ProducedDocument] = []
    for position, name in enumerate(names, 1):
        print(f"[{position}/{len(names)}] {name}")
        try:
            generator: DocumentGenerator = DOCUMENT_REGISTRY.create(name)
            path = naming.path_for(generator.name, generator.extension)
            produced.append(_write_document(generator, request, path))
        except Exception as exc:  # noqa: BLE001 - one document failing must not lose the others
            print(f"Document '{name}' could not be generated: {exc}")

    print("[master] assembling Start Here")
    master = MasterDocument()
    master_request = replace(request, produced=tuple(produced))
    produced.append(
        _write_document(master, master_request, naming.path_for(master.name, master.extension))
    )
    return produced
