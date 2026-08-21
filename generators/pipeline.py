"""Runs the configured document generators, then the master document.

This is what keeps `Engine` from growing a hardcoded block per output
file: adding a document is a new generator module plus a registry name in
config, and nothing here or in `Engine` changes.

Details: docs/dev/generators/pipeline.md#module
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, replace
from typing import List, Sequence

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest, ProducedDocument
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


def _with_banner(output: DocumentOutput, request: DocumentRequest) -> str:
    """Prepend the coverage banner to Markdown *view* outputs only.

    Reads `request.coverage`, computed once by `run_document_pipeline`
    before any generator runs - not a fresh `build_coverage` query per
    document, which is what "computed once per run" (docs/adr/0001)
    actually asks for.

    Done here rather than in each generator so the rule lives in one place
    and a new document gets it by existing. Skipped for any other kind or
    extension: a JSON or YAML file with a Markdown blockquote glued to the
    front is not a JSON or YAML file, and a source/projection/rule-catalog
    document reads as data, not as something a banner introduces.
    Details: docs/dev/generators/pipeline.md#_with_banner
    """
    if output.kind != "view" or output.extension != "md":
        return output.content
    banner = render_coverage_banner(
        request.coverage, stopped_reason=request.settings.get("stopped_reason", "")
    )
    return f"{banner}\n{output.content}"


def _write_document(
    generator: DocumentGenerator, request: DocumentRequest, naming: DocumentNaming
) -> List[ProducedDocument]:
    """Build every file one generator produces and write each to disk.
    Raises whatever the generator raises - `run_document_pipeline` owns the
    decision to degrade rather than abort.
    Details: docs/dev/generators/pipeline.md#_write_document
    """
    produced = []
    for output in generator.outputs(request):
        path = naming.path_for(output.filename, output.extension)
        content = _with_banner(output, request)
        write_output(path, content)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        # Forward slashes always, regardless of host OS - this is a
        # Markdown link another document embeds, not a filesystem path.
        relative_link = os.path.relpath(path, naming.out_dir).replace(os.sep, "/")
        produced.append(
            ProducedDocument(
                name=generator.name, title=generator.title, purpose=generator.purpose,
                path=path, kind=output.kind, checksum=checksum, filename=output.filename,
                relative_link=relative_link,
            )
        )
    return produced


def run_document_pipeline(
    request: DocumentRequest, naming: DocumentNaming, names: Sequence[str]
) -> List[ProducedDocument]:
    """Generate every document in `names`, then the master document.

    Args:
        request: the base request handed to each generator. Its `produced`
            must be empty - this function fills it in for the master
            document's own request and for no one else. Its `coverage` is
            overwritten unconditionally, computed fresh here regardless of
            whatever the caller passed.
        naming: where this run's files go and how they are named.
        names: registry names of the documents to generate, in order.

    Returns:
        One `ProducedDocument` per file actually written - one for a
        single-output generator, several for one producing a source/view
        split - master document's own output(s) last. A generator that
        fails is logged and skipped, not raised - the same "degrade this
        one output, don't abort the run" discipline `GraphPRDSynthesizer`
        already applies per page. A document that failed is absent from the
        list, so the master document never links to a file that isn't there.
    Details: docs/dev/generators/pipeline.md#run_document_pipeline
    """
    # Announced per document, not just as a batch: generator cost is wildly
    # uneven - most are deterministic and instant, while "prd" and "gherkin"
    # each make a model call per page/scenario. A single "generating N
    # documents" line would hide an hour inside one of them.
    # Details: research/plan-progreso-en-terminal.md
    print(f"\nGenerating {len(names)} documents, then the master document...")
    # Computed once, here - not per document. `coverage`'s own generator
    # and every Markdown document's banner both read `request.coverage`
    # rather than each running their own `build_coverage` query.
    request = replace(request, coverage=build_coverage(request.graph_store))
    produced: List[ProducedDocument] = []
    for position, name in enumerate(names, 1):
        print(f"[{position}/{len(names)}] {name}")
        try:
            generator: DocumentGenerator = DOCUMENT_REGISTRY.create(name)
            produced.extend(_write_document(generator, request, naming))
        except Exception as exc:  # noqa: BLE001 - one document failing must not lose the others
            print(f"Document '{name}' could not be generated: {exc}")

    print("[master] assembling Start Here")
    master = MasterDocument()
    master_request = replace(request, produced=tuple(produced))
    produced.extend(_write_document(master, master_request, naming))
    return produced
