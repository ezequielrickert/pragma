"""Which registered document gets a dedicated Phase B renderer, and
which falls back to the generic template - the audit ADR-0016 point 3
calls for, resolving ticket #123's own first half.

**Verdict, per document, against ADR-0016 point 2's locked bar** (ships
as a single vendorable static asset, one `<script>`/`<link>` tag, no
Node.js toolchain to *use* it; actively maintained; saves meaningfully
more effort than the generic template):

- `openapi` -> **Redoc** (`dashboard/redoc_renderer.py`, ticket #124).
  The exact reference case ADR-0016 point 2 names by name - real,
  single-script, actively maintained.
- Every other document -> **generic**. Checked each real external
  standard this map adopted for a matching single-script embed and
  found none that clears the bar without a Node build step: FINOS
  CALM's own tooling is a Node CLI/webapp, not an embeddable script;
  CycloneDX has viewer tools but none single-script; JSON Schema
  (`data-model`), DTCG (`tokens`), Custom Elements Manifest (`catalog`),
  SARIF (`usability`/`accessibility`), ACT Rules/EARL (same two),
  XState (`flows` - a visualizer exists, but it is an interactive
  online tool, not a static embed), Arazzo, and Gherkin (`gherkin` -
  Cucumber's own HTML formatter needs the full test runner, not a
  static file) all have no standard single-vendorable-asset viewer.
  Every pragma-native document (`coverage`, `evidence-log`,
  `redaction-log`, `change-log`, `test-plan`, `glossary`,
  `content-inventory`, `risk-register`, `performance-baseline`,
  `decisions.adr`, `confidence-summary`) was never going to have a
  third-party renderer to begin with - there is no external standard
  to look one up for.
- `asyncapi`/`i18n-inventory`/`browser-support-matrix` are absent from
  this table entirely: `generate()` always raises for all three
  (ADR-0018/0027/0028), so no file exists for either renderer to ever
  apply to. Not "generic" - genuinely not applicable.

Details: docs/dev/dashboard/renderer_audit.md#module
"""
from __future__ import annotations

from typing import Dict

# {DOCUMENT_REGISTRY name: renderer verdict}. "generic" means the shared
# template in dashboard/generic_template.py; "redoc" means
# dashboard/redoc_renderer.py (the only dedicated renderer today). A
# name absent here - asyncapi/i18n-inventory/browser-support-matrix -
# never produces a file to render at all; see the module docstring.
RENDERER_BY_NAME: Dict[str, str] = {
    "accessibility": "generic",
    "architecture": "generic",
    "catalog": "generic",
    "change-log": "generic",
    "confidence-summary": "generic",
    "content-inventory": "generic",
    "coverage": "generic",
    "data-model": "generic",
    "decisions.adr": "generic",
    "evidence-log": "generic",
    "export": "generic",
    "flows": "generic",
    "gherkin": "generic",
    "glossary": "generic",
    "openapi": "redoc",
    "performance-baseline": "generic",
    "prd": "generic",
    "redaction-log": "generic",
    "risk-register": "generic",
    "test-plan": "generic",
    "tokens": "generic",
    "tree": "generic",
    "usability": "generic",
}


def renderer_for(name: str) -> str:
    """The verdict for `name`, or `"generic"` for anything the audit
    table hasn't been extended for yet - a new document defaults to the
    shared template rather than erroring, the same "unlisted sorts as
    the ordinary case" posture `master_document.py`'s own resolution-order
    table already takes.
    Details: docs/dev/dashboard/renderer_audit.md#renderer_for
    """
    return RENDERER_BY_NAME.get(name, "generic")
