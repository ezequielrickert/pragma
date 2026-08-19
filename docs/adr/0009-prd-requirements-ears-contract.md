# `prd` requirements schema (EARS syntax) and ID stability contract

**Status**: accepted

The format audit's section 3.3 evaluates `prd` as the central document for legacy system reconstruction (FU-2), but currently least trustworthy due to unstable sequential IDs, lack of confidence criteria, and inability to diff between crawl runs or drive granular module exclusion (FU-3). This ADR locks `requirements.json` (JSON Schema draft 2020-12 in EARS syntax) as the single Source Document of truth, introducing deterministic requirement IDs, confidence levels, evidence links, and HITL review status.

Decided, resolving the ticket's four open points:

**1. Deterministic Requirement ID Scheme (`REQ-<hash>`).** Requirement IDs are constructed as `REQ-` followed by a deterministic short hash (e.g. `REQ-a4f9`) derived from the normalized EARS pattern, trigger event, and target component: `hash(ears_pattern + trigger + target)`. This replaces sequential counters (`REQ-0001`), guaranteeing stable IDs across crawl runs regardless of discovery order, enabling clean git diffing and reliable cross-document references.

**2. Full Field Set & Categorical Confidence.** `requirements.json` is validated against JSON Schema draft 2020-12. Each requirement entry specifies:
- `id`: Deterministic `REQ-<hash>` identifier.
- `ears_pattern`: EARS classification (`ubiquitous`, `event_driven`, `unwanted_behavior`, `state_driven`, `optional_feature`).
- `syntax_text`: The canonical EARS requirement sentence (e.g. *"WHEN the user clicks submit, THE SYSTEM SHALL validate credentials"*).
- `confidence`: Categorical enum (`observed` for verified network/HAR traffic, `inferred` for UI heuristic rules, `assumed` for default system conventions).
- `derived_from`: Array of evidence pointers (`interaction:<id>`, `har:<id>`, `screenshot:<id>`).
- `links`: Cross-document reference object containing `screens` (`SCR-<hash>`, ADR-0003), `endpoints`, `scenarios`, `data_entities`, and `depends_on`.
- `coverage_ref`: Pointer to whole-run coverage per ADR-0001.
- `hitl_status`: Review state (`unreviewed`, `approved`, `rejected`).
- `open_questions`: Array of unresolved questions for human review.

```json
{
  "id": "REQ-a4f9",
  "ears_pattern": "event_driven",
  "syntax_text": "WHEN the user submits the login form, THE SYSTEM SHALL authenticate the credentials",
  "confidence": "observed",
  "derived_from": ["interaction:INT-001", "har:req-12"],
  "links": {
    "screens": ["SCR-b2c4"],
    "endpoints": ["POST /api/v1/auth/login"],
    "depends_on": []
  },
  "coverage_ref": { "run_id": "RUN-2026-08-19" },
  "hitl_status": "unreviewed",
  "open_questions": []
}
```

**3. ReqIF 1.2 Export.** ReqIF 1.2 (Requirements Interchange Format XML) export is deferred to the new-document wave as a secondary converter tool. First-wave efforts focus on `requirements.json` as the native typed source and `prd.md` as the human-readable view.

**4. Source / View Document Split.** `requirements.json` is the sole **Source Document** (Capa 2). `prd.md` is a mechanically generated **View Document** (Capa 3) organized by architectural modules (ADR-0007) and HITL review status.

**5. Export Population** (amendment). `requirements.json` entries populate `export.json`'s reserved `Requisito` nodes (ADR-0002). `links.screens`/`links.endpoints` become `implementa` edges, from the citing `Pantalla`/`Endpoint` to the `Requisito`; `links.depends_on` becomes `depende_de` edges between `Requisito` nodes; `links.data_entities` becomes `cubre` edges, from the `Requisito` to its `Entidad` (ADR-0008). `links.scenarios` is left for `gherkin` (#77) to wire once `Escenario` is populated.

Wayfinder ticket: [prd: lock requirements.json schema (EARS)](https://github.com/ezequielrickert/pragma/issues/74), part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
