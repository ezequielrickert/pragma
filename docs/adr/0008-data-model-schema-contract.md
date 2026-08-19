# `data-model` schema, W3C DPV privacy layer, and Mermaid ER contract

**Status**: accepted

The format audit's section 3.8 evaluates `data-model`'s current extraction as undercounting fields present in API traffic but unexposed in HTML forms, and lacking a privacy taxonomy. This ADR locks the `data-model.json` schema (JSON Schema draft 2020-12) as the single Source Document of truth, incorporating W3C Data Privacy Vocabulary (DPV) annotations, multi-source observation provenance, coverage gap citations, and Mermaid `erDiagram` rendering for `data-model.md`.

Decided, resolving the ticket's four open points:

**1. Data Privacy Layer (W3C DPV Alignment).** Fields containing personal data carry a structured `privacy` object specifying W3C DPV taxonomy categories (`dpv_type`: e.g. `dpv:EmailAddress`, `dpv:PersonalIdentifier`, `dpv:FinancialData`) and sensitivity ratings, enabling automated compliance auditing and redaction overlays:

```json
"privacy": {
  "is_pii": true,
  "category": "dpv:PersonalData",
  "dpv_type": "dpv:EmailAddress",
  "sensitivity": "medium"
}
```

**2. Entity & Field Schema (`observed_in`).** `data-model.json` is validated against JSON Schema draft 2020-12. Fields consolidate evidence across three distinct observation points under `observed_in` (`forms`, `api_endpoints`, `ui_state`) rather than relying on HTML forms alone:

```json
"fields": {
  "email": {
    "type": "string",
    "format": "email",
    "nullable": false,
    "confidence": 0.95,
    "observed_in": {
      "forms": ["#loginForm input[name='email']"],
      "api_endpoints": ["POST /api/v1/auth/login", "GET /api/v1/users/me"],
      "ui_state": ["SCR-a4f9"]
    }
  }
}
```

**3. Coverage Gaps Citation (`gaps`).** `data-model.json` embeds a top-level `gaps` array to explicitly document unobserved or partially inferred entities/fields due to unvisited crawl routes, embedding a `coverage_ref` (`run_id`, `unvisited_endpoint`) per ADR-0001:

```json
"gaps": [
  {
    "entity": "PaymentMethod",
    "reason": "unvisited_route",
    "coverage_ref": {
      "run_id": "RUN-2026-08-19",
      "unvisited_endpoint": "POST /api/v1/checkout/pay"
    }
  }
]
```

**4. Source / View Document Split & ER Rendering.** `data-model.json` is the machine-checkable **Source Document** (Capa 2). `data-model.md` is a mechanically generated **View Document** (Capa 3) rendering native Markdown **Mermaid `erDiagram`** blocks for visual entity-relationship navigation without external compilation tools.

**5. Export Population** (amendment). `data-model.json` entities populate `export.json`'s reserved `Entidad` nodes (ADR-0002). Each entity's `observed_in.api_endpoints` citations become `depende_de` edges, from the citing `Endpoint` to its `Entidad`.

Wayfinder ticket: [data-model: lock schema (JSON Schema + DBML/ER + DPV)](https://github.com/ezequielrickert/pragma/issues/73), part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
