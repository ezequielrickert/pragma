"""D12: the document that explains the other documents, plus `llms.txt`
and `manifest.json` (docs/adr/0015).

Runs last, after every ordinary generator, and is the only one that reads
`DocumentRequest.produced` instead of the graph. Deliberately contains no
LLM call: the narrative of what the application *does* is D1's job, and
duplicating it here would produce two documents saying the same thing in
different words. `master.md` answers "there are files in `docs/`, which
one do I open?"; `llms.txt` answers the same question for a model reading
the site instead of a person; `manifest.json` answers "what did this run
actually produce, and what does each file mean?" - all three mechanically
rendered from the identical `request.produced`, never a second,
independently-maintained list.

Details: docs/dev/generators/master_document.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from core.documents import DocumentGenerator, DocumentOutput, DocumentRequest, ProducedDocument
from core.registry import DOCUMENT_REGISTRY
from utils.schema_validation import validate_against_schema

_MANIFEST_SCHEMA_PATH = "schemas/manifest.schema.json"

# The wayfinder map's own ticket-resolution order (docs/adr/0015 point 1) -
# a real established sequence, not an arbitrary alphabetical one. A
# registry name not listed here (a future document, or a locally
# registered test double) sorts after every named one, alphabetically
# among itself, rather than raising - this list is a display order, not a
# completeness gate.
_RESOLUTION_ORDER: Tuple[str, ...] = (
    "coverage", "export", "tree", "openapi", "tokens", "catalog", "architecture",
    "data-model", "prd", "usability", "accessibility", "gherkin", "flows",
)

# The specific external standard and version each non-Markdown file
# validates against (docs/adr/0015 point 2) - a fact about the document
# type itself, known from having implemented it, not derived from the
# file's own bytes. Keyed by `DocumentOutput.filename` (the stem, no
# extension) - the one identifier stable across a run's timestamped path.
# A name absent here (a future document not yet implemented) gets no
# `format` entry rather than a guessed one; add a line when that ticket lands.
_FORMAT_BY_FILENAME: Dict[str, str] = {
    "coverage": "JSON Schema 2020-12",
    "export": "JSON-LD 1.1",
    "tree.aria": "Playwright ariaSnapshot()",
    "tree.axtree": "CDP Accessibility.getFullAXTree",
    "custom-elements": "Custom Elements Manifest 2.1.0",
    "data-model": "JSON Schema 2020-12",
    "tokens": "DTCG v2025.10",
    "architecture.calm": "FINOS CALM 1.2",
    "architecture.cyclonedx": "CycloneDX 1.6",
    "openapi.raw": "OpenAPI 3.1.0",
    "openapi": "OpenAPI 3.1.0",
    "redaction.overlay": "OpenAPI Overlay Specification 1.0.0",
    "requirements": "JSON Schema 2020-12",
    "usability-rules": "ACT Rules Format 1.1",
    "usability.earl": "EARL 1.0",
    "usability.sarif": "SARIF 2.1.0",
    "accessibility-rules": "ACT Rules Format 1.1",
    "accessibility.earl": "EARL 1.0",
    "accessibility.sarif": "SARIF 2.1.0",
    "flows.xstate": "XState v5",
    "flows.arazzo": "Arazzo 1.1.0",
    "gherkin": "Gherkin",
    "evidence-log": "JSON Lines",
    "asyncapi": "AsyncAPI 3.0.0",
    "change-log": "JSON Schema 2020-12",
    "glossary": "SKOS/JSON-LD",
    "redaction-log": "JSON Lines",
    "test-plan": "JSON Schema 2020-12",
    "risk-register": "JSON Schema 2020-12",
    "content-inventory": "JSON Schema 2020-12",
}

# A generator whose filename varies per output - `decisions.adr/0001-...`,
# `decisions.adr/0002-...`, one per inferred/assumed requirement - has no
# single filename `_FORMAT_BY_FILENAME` could ever key on. Checked only
# once an exact match above misses.
_FORMAT_BY_FILENAME_PREFIX: Tuple[Tuple[str, str], ...] = (
    ("decisions.adr/", "MADR 4.0.0"),
)


def _format_for(filename: str) -> str:
    """`_FORMAT_BY_FILENAME`'s exact match, falling back to
    `_FORMAT_BY_FILENAME_PREFIX`'s prefix match, then `""` - a filename
    matching neither gets no `format` entry, same as before this existed.
    Details: docs/dev/generators/master_document.md#_format_for
    """
    if filename in _FORMAT_BY_FILENAME:
        return _FORMAT_BY_FILENAME[filename]
    for prefix, document_format in _FORMAT_BY_FILENAME_PREFIX:
        if filename.startswith(prefix):
            return document_format
    return ""


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

    def generate(self, request: DocumentRequest) -> Tuple[DocumentOutput, ...]:
        manifest = _build_manifest(request)
        validate_against_schema(manifest, _MANIFEST_SCHEMA_PATH)
        return (
            DocumentOutput(filename="master", kind="view", extension="md", content=_render_master(request)),
            DocumentOutput(filename="llms", kind="view", extension="txt", content=_render_llms_txt(request)),
            DocumentOutput(
                filename="manifest", kind="source", extension="json",
                content=json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            ),
        )

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


def _render_master(request: DocumentRequest) -> str:
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
        lines.append(f"## [{document.title}]({document.relative_link})")
        lines.append("")
        lines.append(document.purpose)
        lines.append("")
    lines += MasterDocument._gaps(request)
    return "\n".join(lines)


# --- llms.txt (docs/adr/0015 point 1) ---


def _resolution_rank(name: str) -> Tuple[int, str]:
    try:
        return (_RESOLUTION_ORDER.index(name), "")
    except ValueError:
        return (len(_RESOLUTION_ORDER), name)


def _llms_section(document: ProducedDocument) -> str:
    """`## Source Documents` / `## Views` / `## Optional`
    (docs/adr/0015 point 1). A rule catalog or a tooling-facing
    projection (SARIF, CycloneDX - CI/tooling formats, not something an
    LLM needs to understand the site) is `## Optional`, llmstxt.org's own
    convention for a skippable, lower-priority link.
    Details: docs/dev/generators/master_document.md#_llms_section
    """
    if document.kind in ("rule-catalog", "projection"):
        return "Optional"
    if document.kind == "view":
        return "Views"
    return "Source Documents"


def _render_llms_txt(request: DocumentRequest) -> str:
    """`llms.txt` (docs/adr/0015 point 1) - sections mirroring
    `CONTEXT.md`'s own document taxonomy, links ordered by the map's
    resolution order within each section.
    Details: docs/dev/generators/master_document.md#_render_llms_txt
    """
    by_section: Dict[str, List[ProducedDocument]] = {"Source Documents": [], "Views": [], "Optional": []}
    for document in request.produced:
        by_section[_llms_section(document)].append(document)

    lines = [f"# {request.site}", "", f"> {MasterDocument.purpose}", ""]
    for section in ("Source Documents", "Views", "Optional"):
        documents = by_section[section]
        if not documents:
            continue
        documents = sorted(documents, key=lambda d: (_resolution_rank(d.name), d.filename))
        lines.append(f"## {section}")
        lines.append("")
        lines += [f"- [{document.title}]({document.relative_link}): {document.purpose}" for document in documents]
        lines.append("")
    return "\n".join(lines)


# --- manifest.json (docs/adr/0015 point 2) ---


def _manifest_entry(document: ProducedDocument) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "name": document.name,
        "path": document.relative_link,
        "kind": document.kind,
        "status": "on",
        "checksum": f"sha256:{document.checksum}",
    }
    # A source/view pair from the same generator often shares one
    # `filename` (e.g. both of coverage.json/coverage.md are minted from
    # `filename="coverage"`), so `kind` decides first - the table would
    # otherwise hand the view the source's external-standard format.
    document_format = "Markdown" if document.kind == "view" else _format_for(document.filename)
    if document_format:
        entry["format"] = document_format
    return entry


def _build_manifest(request: DocumentRequest) -> Dict[str, Any]:
    """`manifest.json` (docs/adr/0015 point 2) - one entry per file this
    run actually produced (`status: "on"`), plus one per registered
    document this run's config left off (`status: "off"`, no `path`/
    `kind`/`checksum`/`format` - those describe a real file, and no file
    exists to describe). `status` is never a second, hand-maintained flag:
    it is exactly "was this name's generator in `request.produced`",
    derived at generation time from the pipeline's own real output.
    Details: docs/dev/generators/master_document.md#_build_manifest
    """
    on_names = {document.name for document in request.produced}
    entries = [_manifest_entry(document) for document in request.produced]
    entries += [
        {"name": name, "status": "off"}
        for name in sorted(DOCUMENT_REGISTRY.names())
        if name not in on_names
    ]
    entries.sort(key=lambda entry: (_resolution_rank(entry["name"]), entry.get("path", "")))
    return {"documents": entries}
