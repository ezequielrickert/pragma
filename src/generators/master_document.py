"""D12: the document that explains the other documents.

Runs last, after every ordinary generator, and is the only one that reads
`DocumentRequest.produced` instead of the graph. Deliberately contains no
LLM call: the narrative of what the application *does* is D1's job, and
duplicating it here would produce two documents saying the same thing in
different words. This one answers a different question - "there are nine
files in `docs/`, which one do I open?" - and that answer is deterministic.

Details: docs/dev/generators/master_document.md#module
"""
from __future__ import annotations

from pathlib import Path

from ..core.documents import DocumentGenerator, DocumentRequest


class MasterDocument(DocumentGenerator):
    """Deliberately **not** in `DOCUMENT_REGISTRY`: it is not one of the
    documents a user turns on and off, it is the pipeline's closing step,
    and the pipeline instantiates it directly. Registering it would let it
    be scheduled among the ordinary generators, where its `produced` would
    be half-empty and the output silently wrong.
    Details: docs/dev/generators/master_document.md#masterdocument
    """

    name = "master"
    title = "Start Here"
    purpose = "Index of every document this run produced, and what each one is for."

    def generate(self, request: DocumentRequest) -> str:
        # No coverage banner rendered here: the pipeline prepends it to every
        # Markdown document, this one included.
        # Details: docs/dev/generators/master_document.md#no-own-banner
        lines = [
            f"# {request.site}: generated documentation",
            "",
            "This run produced the documents below. Each one is complete on its own - this page "
            "exists so you know which to open first, not to replace any of them.",
            "",
        ]
        for document in request.produced:
            lines.append(f"## [{document.title}]({Path(document.path).name})")
            lines.append("")
            lines.append(document.purpose)
            lines.append("")
        return "\n".join(lines)
