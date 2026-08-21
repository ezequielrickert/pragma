"""What each registered document actually is and what it's typically
used for, plus one short example of its real shape - the two things
`document.purpose`'s one-line summary alone doesn't carry (ticket #145,
map #142). A reviewer who doesn't already know this pipeline's own
vocabulary can't tell what "Evidence Log" means from its title alone.

Mirrors `dashboard/renderer_audit.py`'s own shape: one lookup table
keyed by `DOCUMENT_REGISTRY` name, a `_for(name)` accessor that degrades
gracefully for an unlisted name rather than erroring, and a completeness
test (`tests/test_document_context.py`) checking every registered name
has a real entry - the same "stays honest by test, not by someone
remembering to update a second file" discipline `docs/dev/`'s own
`tests/test_dev_docs.py` already enforces, deliberately, so this table
doesn't go stale the way `docs/explicativos/` did (see
`.claude/skills/explicativos-sync/SKILL.md`'s own account of that).

Every example below is either lifted from this pipeline's own real test
fixtures/schemas or written generic enough to be honest about the shape
without inventing site-specific facts. `asyncapi`/`i18n-inventory`/
`browser-support-matrix` get no fabricated example: `generate()` always
raises for all three today (ADR-0018/0027/0028, no capture
instrumentation exists yet) - stating a real content shape they never
actually produce would be exactly the invented specificity this
project's own generators avoid.

Details: docs/dev/dashboard/document_context.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Dict, Optional

from core.documents import ProducedDocument

_NOT_YET_PRODUCED = (
    "No capture instrumentation exists yet for this document's data source, so `generate()` "
    "always raises rather than emitting a fabricated example - see this document's own generator "
    "module docstring for exactly what's missing."
)


@dataclass(frozen=True)
class DocumentContext:
    """What a document type is and what it's for, plus one short example
    of its real shape.
    Details: docs/dev/dashboard/document_context.md#documentcontext
    """

    explanation: str
    example: str


CONTEXT_BY_NAME: Dict[str, DocumentContext] = {
    "accessibility": DocumentContext(
        explanation=(
            "Every accessibility problem this crawl could detect mechanically - missing alt text, "
            "unlabeled form fields, insufficient color contrast - as Nielsen-heuristic-style "
            "findings, each cited to the exact component instance it came from. Used to prioritize "
            "a real remediation backlog without re-auditing the site by hand; the SARIF export is "
            "what a CI pipeline or code-review tool would actually ingest."
        ),
        example=(
            '{"id": "usability-rules:contrast-01", "target": "example.com/|button.buy", '
            '"level": "violation", "message": "Text contrast ratio 2.1:1, below WCAG AA 4.5:1"}'
        ),
    ),
    "architecture": DocumentContext(
        explanation=(
            "The application's own module structure and dependency graph as a FINOS CALM document "
            "(nodes + relationships), third-party integrations it actually calls as a CycloneDX "
            "bill of materials, and a rendered arc42 view over both. Used to onboard someone to a "
            "codebase's real shape, or to feed an architecture-governance tool that already reads "
            "CALM/CycloneDX natively."
        ),
        example=(
            '{"nodes": [{"unique-id": "MOD-admin", "node-type": "service", '
            '"name": "admin"}], "relationships": [{"relationship-type": '
            '{"composed-of": {"container": "MOD-admin", "nodes": ["example.com/admin/users"]}}}]}'
        ),
    ),
    "asyncapi": DocumentContext(
        explanation=(
            "Would document any WebSocket/SSE/long-polling message contract the crawl observed, "
            "per AsyncAPI's own schema - for a real-time API the same way openapi.yaml documents "
            "REST endpoints."
        ),
        example=_NOT_YET_PRODUCED,
    ),
    "browser-support-matrix": DocumentContext(
        explanation=(
            "Would document observed technical evidence for legacy-browser support (polyfills, "
            "vendor-prefixed CSS, UA-sniffing branches) plus an optional human-supplied business "
            "reason - a real answer to \"do we actually need to support IE11\" grounded in what the "
            "site's own code does, not a guess."
        ),
        example=_NOT_YET_PRODUCED,
    ),
    "catalog": DocumentContext(
        explanation=(
            "Every reusable UI component this crawl inferred - its props, its visual variants, "
            "which screens it appears on, and which design tokens it cites - as a Custom Elements "
            "Manifest. The input for rebuilding the UI in React/Vue/whatever a migration targets, "
            "component by component rather than screen by screen."
        ),
        example=(
            '{"kind": "class", "name": "SubmitButton", "customElement": false, '
            '"x-tokens": {"color": ["{core.color.surface-1}"], "spacing": []}}'
        ),
    ),
    "change-log": DocumentContext(
        explanation=(
            "A per-entity diff between this run and whichever run preceded it, scoped to every "
            "entity kind that already carries a stable Short-hash ID (screens, requirements, "
            "endpoints, modules, ...). Used to answer \"what changed since last time we crawled "
            "this site\" without diffing 15 documents by hand."
        ),
        example='{"entity_kind": "SCR", "added": ["SCR-a1b2c3"], "removed": [], "run_id_from": null}',
    ),
    "confidence-summary": DocumentContext(
        explanation=(
            "How much of what's in requirements.json/data-model.json/usability's and "
            "accessibility's findings was actually observed versus inferred versus assumed - "
            "rolled up per source document, citing each by reference rather than restating any "
            "individual finding. Used as a quick trust gauge before acting on a specific document."
        ),
        example='{"source": "prd", "by_confidence": {"observed": 12, "inferred": 4, "assumed": 1}}',
    ),
    "content-inventory": DocumentContext(
        explanation=(
            "Every piece of copy, microcopy, and legally-mandated text the crawl found, cited to "
            "the specific component instance it was observed on. A copywriter or legal reviewer "
            "auditing site-wide language starts here, not a fresh screen-by-screen read of the site."
        ),
        example=(
            '{"text": "By continuing you agree to our Terms", "component": '
            '"example.com/checkout|p.legal", "is_legal": true}'
        ),
    ),
    "coverage": DocumentContext(
        explanation=(
            "How much of the application this run actually reached - pages visited versus "
            "discovered, components interacted with versus found, endpoints observed. The ceiling "
            "every other document's own confidence sits under: a requirement extracted from a page "
            "this crawl never visited doesn't exist, because that page was never visited."
        ),
        example='{"pages": {"finished": 42, "total": 47}, "endpoints": {"observed": 18}}',
    ),
    "data-model": DocumentContext(
        explanation=(
            "What the application actually collects, deduced from its own forms - one entity per "
            "form, one field per input, each annotated with a W3C DPV privacy category and which "
            "endpoint/page it was observed on. \"What personal data does this app handle\" answered "
            "from real form fields, for a privacy review that doesn't just take a policy document's "
            "word for it."
        ),
        example=(
            '{"entities": {"checkout": {"fields": {"email": {"dpv_category": "Email", '
            '"observed_in": {"api_endpoints": ["POST api.example.com/checkout"]}}}}}}'
        ),
    ),
    "decisions.adr": DocumentContext(
        explanation=(
            "One MADR-format decision record per inferred-or-assumed classification the crawl "
            "needed to make while extracting requirements - a real trail for \"why does the PRD "
            "say this requirement is inferred, not observed\" instead of that judgment call living "
            "only in a confidence field with no reasoning attached."
        ),
        example=(
            "# 0007: REQ-a1b2c3 classified as inferred\n\n## Context\n\nNo direct traffic evidence "
            "was captured for this requirement's own outcome.\n\n## Decision\n\nClassify as "
            "inferred, citing the form fields that imply it."
        ),
    ),
    "evidence-log": DocumentContext(
        explanation=(
            "A per-run index resolving every `interaction:<id>`/`har:<id>` citation another "
            "document's `derived_from` field points at, back to the real interaction/network "
            "capture it names. This is what turns a citation into something checkable: follow a "
            "claim in another document all the way to the actual evidence behind it."
        ),
        example='{"id": "interaction:a1b2c3", "kind": "interaction", "page_url": "example.com/cart"}',
    ),
    "export": DocumentContext(
        explanation=(
            "The crawl's whole graph - screens, components, endpoints, tokens, modules, "
            "requirements, and how they connect - as one portable JSON-LD file. Used by tooling "
            "that needs to reason across the whole site's structure without re-querying the graph "
            "store directly (this is what `usability`'s own EARL findings cite node ids from)."
        ),
        example='{"@graph": [{"id": "example.com/", "type": "Pantalla", "contiene": ["example.com/|button.buy"]}]}',
    ),
    "flows": DocumentContext(
        explanation=(
            "The UI's own statechart (as XState config) and the API call sequences each flow "
            "triggered (as an Arazzo workflow) - both walked by the crawl itself, including error "
            "branches and dead ends it actually hit. A real user journey shows up here as a state "
            "machine, transitions and all - not a slideshow of screenshots."
        ),
        example='{"id": "example.com", "initial": "home", "states": {"home": {"on": {"CLICK_BUY": "cart"}}}}',
    ),
    "gherkin": DocumentContext(
        explanation=(
            "Executable BDD scenarios - one per recorded interaction pattern, rendered as real "
            "Given/When/Then steps from what the crawl actually did, not hand-written. A `.feature` "
            "file a test runner (Cucumber, Behave, ...) can execute directly, not just read."
        ),
        example=(
            "Scenario: Add item to cart\n  Given the user is on \"/products/1\"\n  When they click "
            "\"Add to Cart\"\n  Then the cart total updates"
        ),
    ),
    "glossary": DocumentContext(
        explanation=(
            "The domain vocabulary that recurs across the application's own data model - one SKOS "
            "concept per field name shared by two or more entities, cross-referencing every "
            "data-model field it was observed as. Settles \"is 'email' here the same concept as "
            "'email' over there\" by pointing at where each was actually seen."
        ),
        example='{"id": "TERM-a1b2c3", "skos:prefLabel": "email", "pragma:observedAs": ["checkout.email", "signup.email"]}',
    ),
    "i18n-inventory": DocumentContext(
        explanation=(
            "Would document locale variants of content-inventory's own copy and glossary's own "
            "terms, ICU MessageFormat-shaped - a real translation-completeness view, so which "
            "strings still need localizing is a fact, not a guess."
        ),
        example=_NOT_YET_PRODUCED,
    ),
    "openapi": DocumentContext(
        explanation=(
            "Every endpoint the crawl actually observed being called, as an OpenAPI 3.1 spec - a "
            "raw private variant, a redaction-overlay-applied variant, and a public variant. Feeds "
            "client-code generators or mock servers exactly like a hand-written spec would; the "
            "difference is it's built from real traffic, not a developer's memory of the API."
        ),
        example='paths:\n  /api/cart:\n    post:\n      responses:\n        "200":\n          description: OK',
    ),
    "performance-baseline": DocumentContext(
        explanation=(
            "Network latency percentiles (p50/p95/p99) per distinct screen template, not per "
            "individual page - a template repeated across 40 product pages gets one baseline, not "
            "40. Used to spot which page *shape* is actually slow, before Core Web Vitals capture "
            "exists to say more."
        ),
        example='{"template_hash": "a1b2c3", "network": {"p50_ms": 120, "p95_ms": 480, "p99_ms": 900}}',
    ),
    "prd": DocumentContext(
        explanation=(
            "Requirements extracted in EARS syntax (\"WHEN ..., THE SYSTEM SHALL ...\") from "
            "observed traffic and declared markup, grouped by module, each with a categorical "
            "confidence (observed/inferred/assumed) and links back to the screens/endpoints/data "
            "entities that justify it. The document a product owner or a rebuild effort actually "
            "starts from."
        ),
        example=(
            '{"id": "REQ-a1b2c3", "syntax_text": "WHEN the user submits the checkout form, THE '
            'SYSTEM SHALL create an order.", "confidence": "observed"}'
        ),
    ),
    "redaction-log": DocumentContext(
        explanation=(
            "Every field openapi's own redaction overlay actually redacted this run, and why - "
            "never the value that got removed. Used to audit that the public OpenAPI variant "
            "really did strip what it claims to, without ever exposing the sensitive value itself "
            "in the audit trail."
        ),
        example='{"path": "components.schemas.User.properties.ssn", "reason": "PII: government id"}',
    ),
    "risk-register": DocumentContext(
        explanation=(
            "Structurally-observable risk flags on architecture.cyclonedx.json's own third-party "
            "services - sparse annotations, never a re-listing of the whole BOM. Real structural "
            "signals (e.g. information-disclosure headers), not a generic security checklist run "
            "against every service regardless of what it actually does."
        ),
        example='{"service_ref": "urn:cdx:...#payments-api", "risk": "missing-security-headers"}',
    ),
    "test-plan": DocumentContext(
        explanation=(
            "Every gherkin scenario, cited by its own tags, paired with a staging outcome - "
            "\"untested\" until a real Cucumber JSON run reports otherwise. A spreadsheet tracking "
            "test coverage drifts from what the scenarios actually check the moment someone edits "
            "one without updating the other; this can't drift, since it's derived from the same "
            "scenarios."
        ),
        example='{"scenario_tag": "@checkout-add-item", "outcome": "untested"}',
    ),
    "tokens": DocumentContext(
        explanation=(
            "The color palette and type scale the site actually renders, ranked by how often each "
            "value is used, as a DTCG-shaped tokens.json (core primitives + semantic aliases). The "
            "real input for rebuilding the UI's visual language - values pulled from the rendered "
            "page, not eyeballed off a screenshot."
        ),
        example='{"core": {"color": {"surface-1": {"$type": "color", "$value": "#2d7737"}}}}',
    ),
    "tree": DocumentContext(
        explanation=(
            "Every screen's accessibility tree - role, accessible name, and hierarchy - the way a "
            "screen reader actually sees the page, straight from Playwright's own ariaSnapshot. "
            "Used to check real semantic structure (is this actually a heading, a button, a "
            "landmark) independent of how it looks visually."
        ),
        example='- heading "Checkout" [level=1]\n  - button "Place order"',
    ),
    "usability": DocumentContext(
        explanation=(
            "Nielsen-heuristic usability findings (inconsistent labeling, missing feedback, "
            "unclear affordances, ...) as an ACT rule catalog plus EARL/JSON-LD findings, with a "
            "mechanical SARIF export. Same role as `accessibility`: a prioritized backlog with a "
            "citation for every entry, not one person's subjective walkthrough notes."
        ),
        example=(
            '{"id": "usability-rules:label-01", "target": "example.com/|input.search", '
            '"level": "warning", "message": "No visible label for search input"}'
        ),
    ),
}


def context_for(name: str) -> Optional[DocumentContext]:
    """The explanation/example for `name`, or `None` for a document this
    table hasn't been extended for yet - the dashboard falls back to
    showing only `document.purpose` rather than a placeholder.
    Details: docs/dev/dashboard/document_context.md#context_for
    """
    return CONTEXT_BY_NAME.get(name)


def render_context_section(document: ProducedDocument) -> str:
    """"About this document" HTML, shared verbatim by both
    `generic_template.py` and `redoc_renderer.py` - one real rendering
    of this table's content rather than two copies that could drift.
    Empty string, not a placeholder, when `context_for` finds nothing.
    Details: docs/dev/dashboard/document_context.md#render_context_section
    """
    context = context_for(document.name)
    if context is None:
        return ""
    return (
        '<div class="context"><h2>About this document</h2>'
        f"<p>{escape(context.explanation)}</p>"
        f'<pre class="example">{escape(context.example)}</pre></div>'
    )
