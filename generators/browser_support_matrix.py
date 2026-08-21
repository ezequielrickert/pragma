"""`browser-support-matrix.json` - locked ready for observed legacy-browser
evidence no instrumentation captures yet, docs/adr/0028.

**Entirely absent today, on purpose.** Detecting a polyfill, a
vendor-prefixed CSS rule, or user-agent-sniffing code needs raw script
and stylesheet text this crawl doesn't capture - `getComputedStyle()`
(`discover_components.js`) always normalizes a vendor-prefixed property
to its standard name, so it structurally cannot see one; no capture
reads `document.styleSheets` beyond `extract_pseudo_styles.js`'s own
narrow `:hover`/`:focus` pass over a fixed property list; no script-source
inspection exists at all. The same situation `asyncapi` (ADR-0018) and
`i18n-inventory` (ADR-0027) already found for their own instrumentation
gaps. `BrowserSupportMatrixDocument.generate` raises rather than
returning an empty-but-valid document; `run_document_pipeline`'s existing
skip-and-log degradation is what turns that into `manifest.json`'s
honest `status: "off"` - no second on/off mechanism.

**What this ticket actually builds**: the evidence/query/business-reason
entry shape, as a real, pure, unit-tested function over synthetic
`TechnicalEvidence` fixtures - ready for whenever a future detection pass
(raw stylesheet-rule scanning, script-source inspection) can supply the
real thing.

**Two-tiered detection, one field split** (point 1). `kind`/`subject`/
`browserslist_query` are what a crawler could observe; `business_reason`
is what only a human knows ("a client's procurement system requires
IE11") - unset by default, filled in by a human reviewer later, reusing
`prd`'s `hitl_status` review-workflow pattern (ADR-0009) rather than a
new HITL mechanism.

**Browserslist query syntax for values, not the whole document shape**
(point 2). A vendor prefix names its own browser family
(`vendor_prefix_query`); user-agent-sniffing code names its browser
directly when the matched substring is a well-known one
(`ua_sniff_query`). A polyfill's mere presence targets an unspecified
range of older browsers - `browserslist_query` stays `None` rather than
inventing a specific version this evidence alone can't determine.

**Citation, not duplication, of `performance-baseline`** (point 3):
`performance_baseline_refs` cites `template_hash`es by reference, empty
by default - correlating one piece of evidence to a specific template
needs a correlation pass this ticket doesn't build.

Details: docs/dev/generators/browser_support_matrix.md#module
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.documents import DocumentGenerator, DocumentRequest
from core.registry import DOCUMENT_REGISTRY

# Vendor CSS prefix to the browser family it targets - real, well-known
# associations (CSS Working Group's own vendor-prefix registry), not a
# guess. `-ms-` also covers legacy Edge (EdgeHTML), which shared Trident's
# prefix; distinguishing the two from a bare prefix alone isn't possible.
_VENDOR_PREFIX_FAMILY: Tuple[Tuple[str, str], ...] = (
    ("-webkit-", "safari"), ("-moz-", "firefox"), ("-ms-", "ie"), ("-o-", "opera"),
)

# A well-known user-agent substring to the browser it identifies - real
# signatures (Trident/MSIE for Internet Explorer, Presto for old Opera),
# not a language model's guess.
_UA_SNIFF_BROWSER: Dict[str, str] = {"MSIE": "ie", "Trident": "ie", "Presto": "opera"}


@dataclass(frozen=True)
class TechnicalEvidence:
    """What a future polyfill/vendor-prefix/UA-sniffing detection pass
    would supply for one observation - synthetic today; no real capture
    produces this yet.
    Details: docs/dev/generators/browser_support_matrix.md#technicalevidence
    """

    kind: str
    subject: str
    browserslist_query: Optional[str] = None
    performance_baseline_refs: Tuple[str, ...] = ()


def vendor_prefix_query(prefixed_property: str) -> Optional[str]:
    """The browser family a vendor-prefixed CSS property implies, or
    `None` when the prefix isn't one of the four real vendor prefixes.
    Details: docs/dev/generators/browser_support_matrix.md#vendor_prefix_query
    """
    for prefix, family in _VENDOR_PREFIX_FAMILY:
        if prefixed_property.startswith(prefix):
            return family
    return None


def ua_sniff_query(matched_substring: str) -> Optional[str]:
    """The browser a user-agent-sniffing substring identifies, or `None`
    for a substring this table doesn't recognize.
    Details: docs/dev/generators/browser_support_matrix.md#ua_sniff_query
    """
    return _UA_SNIFF_BROWSER.get(matched_substring)


def build_browser_support_matrix(evidence: Sequence[TechnicalEvidence]) -> List[Dict[str, Any]]:
    """One entry per observed piece of technical evidence -
    `business_reason` always `None` (ADR-0028 point 1: nothing here is
    inferable from the site, only a human review pass fills it in).
    Details: docs/dev/generators/browser_support_matrix.md#build_browser_support_matrix
    """
    return [
        {
            "kind": item.kind,
            "subject": item.subject,
            "browserslist_query": item.browserslist_query,
            "business_reason": None,
            "performance_baseline_refs": list(item.performance_baseline_refs),
        }
        for item in evidence
    ]


@DOCUMENT_REGISTRY.register("browser-support-matrix")
class BrowserSupportMatrixDocument(DocumentGenerator):
    """Registered so `manifest.json` can enumerate it as `status: "off"`
    (the same posture ADR-0018/ADR-0027 already established) - not so it
    can actually run. `generate` always raises; there is no store method
    to call `build_browser_support_matrix` with, since no capture
    instrumentation exists to have written one against.
    Details: docs/dev/generators/browser_support_matrix.md#browsersupportmatrixdocument
    """

    name = "browser-support-matrix"
    title = "Browser Support Matrix"
    purpose = (
        "Observed technical evidence for legacy-browser support (polyfills, vendor prefixes, "
        "UA-sniffing) plus an optional human-supplied business reason - absent until capture "
        "instrumentation for any of the three exists."
    )

    def generate(self, request: DocumentRequest) -> str:
        raise NotImplementedError(
            "browser-support-matrix.json has no capture instrumentation yet (docs/adr/0028 point 1) - "
            "polyfill/vendor-prefix/UA-sniffing detection is a future effort, out of this map's scope."
        )
