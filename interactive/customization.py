"""ADR-0031's "effective document" lookup and customized-document
writer - the one place every consumer of a site's documents (the
interactive dashboard's editor, its chat) resolves a document's
current content through, so `customized/` vs. the original crawl
output is never a per-caller decision.

**Filenames, not `runs.json`.** A site's real produced files are found
by globbing `{slug}_*` under `out_dir` directly, never by trusting
`runs.json`'s own `document_paths` - that dict is keyed by `Document.
Generator.name` (the registry key), and a multi-output generator
(`tokens`, `flows`, ...) writes several `ProducedDocument`s sharing one
`name` but different `filename`/`extension`, so `document_paths`
silently keeps only whichever one iterated last (a known gap, noted as
fog on map #94 before this ticket - not fixed here, just not relied on).
`(filename, extension)` is the real, collision-free identity of one
physical file `generators/pipeline.py::DocumentNaming.path_for` writes.

**Customized files are flat, not per-site subdirectories.** Matches
`DocumentNaming`'s own `{slug}_{filename}_{timestamp}.{extension}`
convention minus the timestamp (a customized document isn't a per-run
artifact) - see ADR-0031's own "Update" callout for why this differs
from what that ADR originally said before this ticket implemented it.

Details: docs/dev/interactive/customization.md#module
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from utils.schema_validation import validate_against_schema
from utils.urls import slugify

# Every produced-document filename this pipeline validates with a
# vendored JSON Schema (utils/schema_validation.py), so an edit can be
# checked the same way its own generator already checks it. Absent
# here means "no known schema" - a customized copy still gets written,
# just without a validation gate (openapi.yaml uses a dedicated
# OpenAPI validator instead, not this generic one; gherkin/master/llms
# carry no schema at all).
SCHEMA_PATH_BY_FILENAME: Dict[str, str] = {
    "accessibility-rules": "schemas/accessibility-rules.schema.json",
    "accessibility.earl": "schemas/accessibility.earl.schema.json",
    "accessibility.sarif": "schemas/accessibility.sarif.schema.json",
    "architecture.calm": "schemas/architecture.calm.schema.json",
    "architecture.cyclonedx": "schemas/architecture.cyclonedx.schema.json",
    "change-log": "schemas/change-log.schema.json",
    "confidence-summary": "schemas/confidence-summary.schema.json",
    "content-inventory": "schemas/content-inventory.schema.json",
    "coverage": "schemas/coverage.schema.json",
    "custom-elements": "schemas/custom-elements.schema.json",
    "data-model": "schemas/data-model.schema.json",
    "evidence-log": "schemas/evidence-log.schema.json",
    "export": "schemas/export.schema.json",
    "flows.arazzo": "schemas/flows.arazzo.schema.json",
    "flows.xstate": "schemas/flows.xstate.schema.json",
    "glossary": "schemas/glossary.schema.json",
    "manifest": "schemas/manifest.schema.json",
    "performance-baseline": "schemas/performance-baseline.schema.json",
    "redaction-log": "schemas/redaction-log.schema.json",
    "requirements": "schemas/requirements.schema.json",
    "risk-register": "schemas/risk-register.schema.json",
    "test-plan": "schemas/test-plan.schema.json",
    "tokens": "schemas/tokens.schema.json",
    "tree.aria": "schemas/tree.aria.schema.json",
    "tree.axtree": "schemas/tree.axtree.schema.json",
    "usability-rules": "schemas/usability-rules.schema.json",
    "usability.earl": "schemas/usability.earl.schema.json",
    "usability.sarif": "schemas/usability.sarif.schema.json",
}

_PRODUCED_FILENAME = re.compile(r"^(?P<filename>.+)_(?P<timestamp>\d{8}T\d{6}Z)\.(?P<extension>[a-z0-9]+)$")


@dataclass(frozen=True)
class SiteOutput:
    """Where one site's documents live - `out_dir` + `site`, the pair
    every function below needs, bundled per python-clean-code's F1
    (max 3 args) rather than threaded through each signature
    separately.
    Details: docs/dev/interactive/customization.md#siteoutput
    """

    out_dir: str
    site: str


@dataclass(frozen=True)
class DocumentRef:
    """One real, distinct produced file - `(filename, extension)` is
    what `DocumentNaming.path_for` actually names a file by, not the
    registry `name` a multi-output generator shares across several.
    Details: docs/dev/interactive/customization.md#documentref
    """

    filename: str
    extension: str


def available_documents(where: SiteOutput) -> List[DocumentRef]:
    """Every distinct file already produced for `where.site`, newest
    run only - found by globbing, not `runs.json` (see module
    docstring).
    Details: docs/dev/interactive/customization.md#available_documents
    """
    slug = slugify(where.site)
    prefix = f"{slug}_"
    seen: Dict[tuple, DocumentRef] = {}
    for path in Path(where.out_dir).glob(f"{slug}_*"):
        if not path.name.startswith(prefix):
            continue
        match = _PRODUCED_FILENAME.match(path.name[len(prefix):])
        if not match:
            continue
        key = (match["filename"], match["extension"])
        seen[key] = DocumentRef(filename=match["filename"], extension=match["extension"])
    return sorted(seen.values(), key=lambda ref: (ref.filename, ref.extension))


def _original_path(where: SiteOutput, ref: DocumentRef) -> Optional[str]:
    """The most recent run's own file for `ref` - `None` if this site
    never produced one. Sorted lexicographically, which sorts
    correctly by time too: the embedded timestamp is
    `YYYYMMDDTHHMMSSZ`.
    Details: docs/dev/interactive/customization.md#_original_path
    """
    slug = slugify(where.site)
    matches = sorted(Path(where.out_dir).glob(f"{slug}_{ref.filename}_*.{ref.extension}"))
    return str(matches[-1]) if matches else None


def customized_path(where: SiteOutput, ref: DocumentRef) -> str:
    """Where an edited copy of `ref` lives - always this one path,
    overwritten on every save, never one file per edit (ADR-0031 point
    2).
    Details: docs/dev/interactive/customization.md#customized_path
    """
    slug = slugify(where.site)
    return f"{where.out_dir}/customized/{slug}_{ref.filename}.{ref.extension}"


def effective_content(where: SiteOutput, ref: DocumentRef) -> Optional[str]:
    """The customized copy if one exists, else the original - ADR-0031's
    own read-time-resolution rule, in one place so no caller re-derives
    it. `None` when neither exists.
    Details: docs/dev/interactive/customization.md#effective_content
    """
    customized = Path(customized_path(where, ref))
    if customized.exists():
        return customized.read_text(encoding="utf-8")
    original = _original_path(where, ref)
    return Path(original).read_text(encoding="utf-8") if original else None


def schema_path_for(filename: str) -> Optional[str]:
    """`SCHEMA_PATH_BY_FILENAME.get(filename)` - `None` for a document
    this table hasn't been extended for (or that validates a different
    way entirely, like `openapi.yaml`'s own OpenAPI-spec validator).
    Details: docs/dev/interactive/customization.md#schema_path_for
    """
    return SCHEMA_PATH_BY_FILENAME.get(filename)


def _parse_for_validation(content: str, extension: str) -> Any:
    """The shape `jsonschema.validate` needs to check `content` against
    - `.yaml` parses as one document (`tree.aria.yaml`), `.jsonl`
    parses as an array of its own lines (the schema validates the row
    list, not the newline-delimited file - `generators/evidence_log.py`'s
    own module docstring says so), everything else as one JSON document.
    Details: docs/dev/interactive/customization.md#_parse_for_validation
    """
    if extension == "yaml":
        return yaml.safe_load(content)
    if extension == "jsonl":
        return [json.loads(line) for line in content.splitlines() if line.strip()]
    return json.loads(content)


def save_customized(where: SiteOutput, ref: DocumentRef, content: str) -> None:
    """Write `content` as `ref`'s customized copy - validated against
    its own real schema first when one exists (ADR-0031 point 2:
    always schema-valid, never a drifting override). Raises
    `jsonschema.ValidationError` or a parse error on invalid input; the
    caller turns that into a real response, this function doesn't.
    Details: docs/dev/interactive/customization.md#save_customized
    """
    schema_path = schema_path_for(ref.filename)
    if schema_path is not None:
        validate_against_schema(_parse_for_validation(content, ref.extension), schema_path)
    path = Path(customized_path(where, ref))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
