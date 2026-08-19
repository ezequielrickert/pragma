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
from typing import List

from core.documents import DocumentGenerator, DocumentRequest


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
        lines += self._gaps(request)
        return "\n".join(lines)

    @staticmethod
    def _gaps(request: DocumentRequest) -> List[str]:
        """What this run did not produce, and why - stated only when true.

        The coverage banner says how much of the site was reached; this says
        which *kinds* of question the document set does not answer at all.
        A reader who does not find an accessibility audit should learn that
        none is produced, rather than assume they lost a file.

        Conditional on the document actually being absent, so that reviving
        D11 makes this note disappear on its own instead of becoming a lie
        that has to be remembered.
        Details: docs/dev/generators/master_document.md#_gaps
        """
        produced_names = {document.name for document in request.produced}
        if "accessibility" in produced_names:
            return []
        return [
            "## Not covered by this run",
            "",
            "**No WCAG / accessibility audit.** Producing one means running axe-core against each "
            "page at a realistic viewport with images enabled, which is a separate measurement "
            "pass this pipeline does not have. The usability audit overlaps it slightly - missing "
            "input types, unexplained disabled controls - but is Nielsen-heuristic work, not a "
            "conformance check, and must not be read as one.",
            "",
            "Contrast ratios, touch-target sizes and spacing scales are absent for the same "
            "reason: they are absolute thresholds, and the crawl measures geometry at 800x600 "
            "with images blocked. Comparisons that are *relative* - these three buttons disagree "
            "with each other - survive that and are reported.",
            "",
        ]
