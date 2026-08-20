# `DocumentGenerator` gains a multi-file, kind-tagged `outputs()` layer over `generate()`

**Status**: accepted

Every ADR in [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64)
(`docs/adr/0001` through `0029`) assumes a document can be a source/view split, or more (`architecture`,
`flows`, `usability`, `accessibility` each need two or three source files plus a view). Confirmed
against the actual code: `DocumentGenerator.generate()` returned exactly one `str`, and
`generators/pipeline.py`'s `_write_document`/`DocumentNaming.path_for` built exactly one path per
generator. Nothing in the codebase could express what nearly every ADR in this map already locked.

Decided, resolving the foundational ticket's open points:

**1. `DocumentOutput` and a Concrete `outputs()` Layer, Not a Breaking Signature Change.**
`generate()` keeps its existing contract — a subclass returns a plain `str` — but its declared
return type widens to `Union[str, Tuple[DocumentOutput, ...]]`, and a new concrete method,
`outputs()`, normalizes the result: a `str` gets wrapped into one `DocumentOutput` automatically,
a tuple is used as-is. `generators/pipeline.py` calls `outputs()`, never `generate()` directly.
Every one of the ~17 existing single-file generators keeps working with zero code changes — the
wrapping happens once, in the base class, not per subclass.

**2. `DocumentOutput` Carries What `CONTEXT.md` Already Named.** `filename` (stem, no extension),
`kind` (`source`/`view`/`projection`/`rule-catalog` — the exact taxonomy `CONTEXT.md`'s glossary
already defines), `extension`, `content`. `filename` is independent of the registry name: `catalog`'s
real output is `custom-elements.json` (ADR-0006), already a different string from its registry key
today, confirming per-output filenames were always the right shape, not a new complication.

**3. `path_for` Unchanged, Applied Per-Output.** `DocumentNaming.path_for(name, extension)` keeps its
exact signature and `{slug}_{name}_{timestamp}.{extension}` wrapper — now called once per
`DocumentOutput` inside `_write_document`'s loop instead of once per generator. No output gets
special-cased path treatment; `openapi.raw.yaml`, `redaction.overlay.yaml`, and `openapi.yaml` are
three ordinary calls to the same function.

**4. Banner Gating Moves to Kind and Extension, Not Extension Alone.** `_with_banner` now checks
`output.kind == "view" and output.extension == "md"` instead of the generator-level
`extension != "md"`. For every currently-legacy generator (auto-wrapped with `kind="view"`), this is
behaviorally identical to today — the `kind` check is a no-op until a new-style generator emits a
non-view Markdown output, which none do yet. The banner's own swap from live `graph_store` queries to
reading `coverage.json` (ADR-0001's actual ask) is `coverage`'s own implementation ticket's job, not
this one's — it needs `coverage.json` to exist first.

**5. Checksum, Wired Once.** `ProducedDocument` gains `kind` and `checksum` fields (both defaulted,
so existing test fixtures constructing `ProducedDocument` by keyword still work unchanged).
`_write_document` computes `hashlib.sha256(content).hexdigest()` at write time, once, shared across
every generator — not reimplemented per document once `master`'s `manifest.json` ticket needs it.

**6. Two New Shared Utilities.** `utils/short_hash.py::short_hash(value: str) -> str` —
`sha1(...)[:10]`, the one implementation behind every `<hash>`-suffixed ID this pipeline mints
(pinned by ADR-0015). Takes one pre-composed string, not `*parts` with implicit joining — callers own
their own composition (`short_hash(f"{method} {host}{path}")`), not a hidden formatting rule inside
the utility. `utils/schema_validation.py::validate_against_schema(data, schema_path)` — wraps
`jsonschema.validate`, one call every source-document generator can make against its own vendored
schema file. `jsonschema==4.23.0` added to `requirements.txt`; CALM, CycloneDX, SARIF, AsyncAPI,
OpenAPI, ACT Rules, Custom Elements Manifest, and DTCG all publish an official JSON Schema, so this
one dependency covers nearly everything this map's later tickets will validate.

Wayfinder ticket: [architecture: design DocumentGenerator's multi-file/kind-tagged output contract](https://github.com/ezequielrickert/pragma/issues/95),
part of [Implement the doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/94).
