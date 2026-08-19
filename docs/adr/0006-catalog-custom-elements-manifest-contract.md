# `catalog` adopts Custom Elements Manifest contract and folds in `catalog-data`

**Status**: accepted

The format audit's section 3.6 evaluates `catalog`'s off-by-default `catalog-data.json` and prose `catalog.md` as a duplicate view anti-pattern. This ADR locks the Custom Elements Manifest (CEM) standard specification for `custom-elements.json` as the single Source Document of truth, folding in `catalog-data`, and converting `catalog.md` into a mechanically rendered View Document.

Decided, resolving the ticket's four open points:

**1. Custom Elements Manifest Schema & Source/View Split.** `custom-elements.json` (adhering to the W3C Web Components Community Group Custom Elements Manifest schema) becomes the single, machine-checkable **Source Document** (Capa 2). `catalog.md` is a mechanically generated **View Document** (Capa 3) rendering component cards, variant tables, screen locations, and consumed design tokens. `catalog-data.json` is deprecated and absorbed into `custom-elements.json`.

**2. `x-observed-variants` Extension.** Added under each component declaration in `custom-elements.json` to capture visual and state variants discovered during crawl runs, linking screens (`SCR-<hash>`, per ADR-0003), triggers, and HAR/screenshot evidence pointers:

```json
"x-observed-variants": [
  {
    "variant_id": "primary-button",
    "attributes": { "class": "btn-primary", "disabled": false },
    "screens": ["SCR-a4f9"],
    "triggers": ["interaction:INT-003"],
    "evidence": ["har:req-42"]
  }
]
```

**3. `x-region` Extension (Screen Landmark Linking).** Connects a catalog component to its semantic ARIA/DOM location in `tree` (ADR-0003), including landmark path, ARIA role, and JSON Pointer into the CDP AXTree JSON (`axtree_ref`):

```json
"x-region": {
  "screen_id": "SCR-a4f9",
  "landmark_path": "main > form[name='login'] > div.actions",
  "aria_role": "button",
  "axtree_ref": "/nodes/14"
}
```

**4. `x-tokens` Extension (Design Tokens Linking).** Connects catalog component styling to `tokens.json` (ADR-0005) by citing DTCG alias references directly (`"{semantic.color.brand-primary}"`), preventing silos between component catalog and design token documentation:

```json
"x-tokens": {
  "color": ["{semantic.color.brand-primary}"],
  "spacing": ["{core.spacing.padding-md}"]
}
```

Wayfinder ticket: [catalog: lock Custom Elements Manifest contract](https://github.com/ezequielrickert/pragma/issues/70), part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
