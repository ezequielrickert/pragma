# `tokens` adopts DTCG v2025.10 contract and folds in `tokens-data`

**Status**: accepted

The format audit's section 3.7 evaluates `tokens`' off-by-default `tokens-data.json` and prose `tokens.md` as a duplicate view anti-pattern. This ADR locks the Design Tokens Community Group (DTCG v2025.10) specification for `tokens.json` as the single Source Document of truth, folding in `tokens-data`, and converting `tokens.md` into a mechanically rendered View Document.

Decided, resolving the ticket's four open points:

**1. DTCG Structure & Core/Semantic Split.** `tokens.json` adheres to DTCG v2025.10 format using two top-level groups within the same document: `"core"` for raw primitive values (e.g. Hex colors, pixel sizes) and `"semantic"` for aliased intent-based tokens (e.g. brand colors, component roles). Aliases use standard DTCG reference syntax (`"{core.color.blue-500}"`):

```json
{
  "core": {
    "color": {
      "blue-500": { "$type": "color", "$value": "#3b82f6" }
    }
  },
  "semantic": {
    "color": {
      "brand-primary": { "$type": "color", "$value": "{core.color.blue-500}" }
    }
  }
}
```

**2. Usage-Frequency Tracking.** Stored under `$extensions.pragma.usage_frequency` for each token. Captures observation counts (`count`) across the crawl and flags design-system candidates (`is_system_candidate: true`, threshold `count >= 3`), separating real design tokens from incidental or one-off inline styles:

```json
"$extensions": {
  "pragma": {
    "usage_frequency": {
      "count": 42,
      "is_system_candidate": true
    }
  }
}
```

**3. Source Trazability Extension (`$extensions.pragma.source`).** Captures CSS provenance for extracted tokens, including source stylesheets, CSS custom property names (`--var-name`), matching DOM selectors, and inline style counts:

```json
"$extensions": {
  "pragma": {
    "source": {
      "stylesheets": ["https://example.com/assets/main.css"],
      "css_variables": ["--primary-color"],
      "selectors": [".btn-primary", "header.hero"],
      "inline_style_count": 0
    }
  }
}
```

**4. Source / View Document Split.** `tokens.json` is the sole, machine-checkable **Source Document** (Capa 2). `tokens.md` is a mechanically generated **View Document** (Capa 3) that renders visual swatch tables for candidates with `is_system_candidate: true`, relegating one-off styles to a secondary appendix. `tokens-data.json` is deprecated and absorbed into `tokens.json`.

**5. Export Population** (amendment). `tokens.json` entries populate `export.json`'s reserved `Token` nodes (ADR-0002). `catalog`'s `x-tokens` links (ADR-0006) become the `usa_token` edge, from each `Componente` to the `Token` nodes it references.

Wayfinder ticket: [tokens: lock DTCG contract](https://github.com/ezequielrickert/pragma/issues/69), part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
