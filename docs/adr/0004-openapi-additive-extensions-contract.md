# `openapi` adopts OpenAPI 3.1.0 and locks additive extensions

**Status**: accepted

The format audit's section 3.5 evaluates `openapi` as the best-scoring document in the pipeline, needing additive extensions rather than a format migration. This ADR locks OpenAPI 3.1.0 adoption, vendor extension schemas (`x-observed-roles`, `x-inference`), non-destructive redaction workflow via OpenAPI Overlays, and linting rules.

Decided, resolving the ticket's five open points:

**1. OpenAPI Version & Scope.** Adopt **OpenAPI 3.1.0** (upgrading from 3.0.3) for 1:1 compatibility with JSON Schema draft 2020-12 (the schema version locked in ADR-0001 for `coverage.json`). Top-level `webhooks` object is reserved in the schema contract but omitted in v1 output, as current crawler instrumentation captures client-server HTTP interactions.

**2. `x-observed-roles` Extension.** Added per operation to declare role-based access observations. Structured with explicit `allowed` and `denied` lists, including HTTP response status codes and evidence pointers (`interaction:<id>`, `har:<id>`):

```yaml
x-observed-roles:
  allowed:
    - role: "admin"
      evidence: ["interaction:INT-001", "har:req-12"]
  denied:
    - role: "guest"
      status_code: 403
      evidence: ["interaction:INT-005"]
```

**3. `x-inference` Extension.** Added per operation to explicitly distinguish observed traffic from inferred paths and schemas, providing granular confidence metrics:

```yaml
x-inference:
  observation_count: 14
  methods_observed: ["GET", "POST"]
  methods_inferred: ["PUT"]
  confidence:
    path_params: 0.95
    request_schema: 0.88
    response_schema: 0.92
```

**4. Non-Destructive Redaction Workflow.** Adopt the **OpenAPI Overlay Specification 1.0.0**. The crawler generator produces `openapi.raw.yaml` (private), against which a `redaction.overlay.yaml` is applied to strip or sanitize sensitive payload properties non-destructively, producing the public `openapi.yaml`.

**5. Quality Linter Ruleset.** Enforce validation via **vacuum** / **Spectral** using the base OpenAPI 3.1 ruleset (`oas3-schema`, `operation-success-response`, `path-declarations-must-exist`, `operation-operationId-unique`) plus custom pragma rules validating the presence and shape of `x-inference`.

Wayfinder ticket: [openapi: lock additive extensions](https://github.com/ezequielrickert/pragma/issues/68), part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
