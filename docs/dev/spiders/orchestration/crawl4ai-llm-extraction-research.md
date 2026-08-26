# crawl4ai `LLMExtractionStrategy` config for a local, weak, non-JSON-mode model

Research for issue [#253](https://github.com/ezequielrickert/pragma/issues/253), part of map
[#251](https://github.com/ezequielrickert/pragma/issues/251) ("Adopt an LLM-driven strategy for
crawl navigation and per-page component extraction"). Findings only — no implementation.
Investigated against the actually-installed `crawl4ai==0.9.2` source in this repo's `.venv`
(`.venv/lib/python3.11/site-packages/crawl4ai/`), confirmed via
`python3 -c "import crawl4ai; print(crawl4ai.__file__)"` →
`/Users/ezequielrickert/projects/pragma/.venv/lib/python3.11/site-packages/crawl4ai/__init__.py`,
cross-checked against docs.crawl4ai.com and docs.litellm.ai where the installed source was
silent or ambiguous.

**Correction (post-close, verified against this repo's actual `.env`):** the base URL/auth
guidance below used `agents/local_agent.py`'s hardcoded LAN-IP fallback instead of this repo's
actually configured endpoint. `.env` is gitignored, so whatever session produced this research
never saw it. The real deployed endpoint is a Tailscale-tunneled, **auth-required** server
(`LOCAL_API_URL` in `.env`; `pragma.yaml`'s own comment confirms the tunnel "requires
`LOCAL_API_KEY` in `.env` for auth"). Applying this doc's own `base_url` rule (strip the
trailing `/chat/completions`) to the real URL gives the tunnel host's `/v1` root, and
`api_token` must be the real `LOCAL_API_KEY` value (read via `os.getenv` at call time — never
hardcode it in code, a doc, or a ticket comment), not a placeholder. Every LAN-IP/placeholder
reference below is the fallback case only (e.g. a bare LM Studio instance with no tunnel in
front of it) — substitute the real tunnel URL + real key for this repo's actual pilot run
(#254).

## Bottom line

- **Provider string**: `"openai/google/gemma-4-e2b"` (LiteLLM's `openai/<model>` prefix — the
  part after the first `/` is passed through verbatim as the model name, so a slashy model id
  is fine). **Always pass a non-empty `api_token`** — for this repo's actual deployment that
  means the real `LOCAL_API_KEY` (the tunnel requires it; see correction above), not a
  placeholder — leaving it empty makes `LLMConfig` fall back to `os.getenv("OPENAI_API_KEY")`,
  which is `None` in this repo's local setup, and litellm's OpenAI client raises rather than
  calling an unauthenticated server. `base_url` should be the tunnel server's `/v1` root (see
  correction above — no trailing `/chat/completions`); litellm's OpenAI-client code path
  appends the endpoint path itself.
- **Schema-based extraction, not instruction-only.** crawl4ai's instruction-only prompt
  (`PROMPT_EXTRACT_BLOCKS_WITH_INSTRUCTION`) hardcodes the output shape to
  `{"index": int, "tags": [...], "content": [str, ...]}` regardless of what the instruction
  asks for — it cannot be steered onto `DESCRIPTIVE_COMPONENT_FIELDS`. Only the schema path
  (`extraction_type="schema"`, `schema=<JSON-schema dict>`) lets the field list drive the
  output shape, via `PROMPT_EXTRACT_SCHEMA_WITH_INSTRUCTION`. `extraction_type` already
  defaults to `"schema"`; just supply `schema`.
- **Chunking**: keep `input_format="markdown"` (not `"html"`/`"cleaned_html"`/`"fit_html"` —
  those three force `IdentityChunking`, i.e. the *entire* page as one LLM call, which a small
  local model with a small context window cannot reliably survive). Leave the pre-chunker at
  its default `RegexChunking()` (paragraph splits on `\n\n`, no duplication) rather than
  switching to `SlidingWindowChunking` — sliding-window chunks intentionally overlap words
  across chunks, which duplicates content into every LLM call and increases both prompt size
  and duplicate-object risk for a model already prone to malformed output. Set
  `chunk_token_threshold` well below the library default of 2048 (start around
  `512`–`768`) and `overlap_rate` low (`0.0`–`0.05`) — the real per-call chunk size is
  decided by `LLMExtractionStrategy`'s internal `merge_chunks` re-grouping
  (`chunk_token_threshold` / `overlap_rate` / `word_token_rate`), not by the pre-chunker.
- **No JSON-repair, no re-prompt-on-malformed-output.** crawl4ai's own failure path is a
  brace-depth string splitter (`split_and_parse_json_objects`) that salvages whichever
  top-level `{...}` segments happen to be valid JSON and drops the rest into a single
  `{"error": true, "tags": ["error"], "content": <raw unparsed text>}` block — no LLM retry, no
  `json_repair`/`json5`-style library, no `response_format` fallback. The only retry loop
  (`perform_completion_with_backoff` / `aperform_completion_with_backoff` in `utils.py`) is
  keyed on `litellm.exceptions.RateLimitError`, not on parse failure. **This project will need
  its own retry/repair wrapper** around `LLMExtractionStrategy` (or an outer per-chunk retry
  that inspects `blocks` for `error: true` entries and re-calls with a corrective follow-up
  prompt) if the malformed-JSON rate from `gemma-4-e2b` turns out to be non-trivial — crawl4ai's
  built-in salvage is a floor, not a fix.
- Do **not** set `force_json_response=True`. It adds `response_format={"type":
  "json_object"}` to the litellm `completion()` call, which `agents/local_agent.py`'s own
  plain chat-completions contract confirms this local server does not support; sending an
  unsupported param risks the request being rejected outright rather than degrading
  gracefully. Leave it `False` and rely on the default `<blocks>...</blocks>`-wrapped prompt,
  which only requires the model to emit a JSON array between two literal XML tags — a much
  softer constraint than strict JSON-mode.

## Question 1 — LiteLLM provider string, `base_url`, `api_token` wiring

`LLMExtractionStrategy.extract`/`aextract` calls `perform_completion_with_backoff`/
`aperform_completion_with_backoff` (`extraction_strategy.py:684-695`, `:887-898`), which does
`from litellm import completion; response = completion(model=provider, ..., api_key=api_token,
base_url=base_url, ...)` (`utils.py:1777-1795`) — `LLMConfig.provider` is passed straight
through as litellm's `model=` string, so whatever crawl4ai/litellm accepts there is exactly
what litellm's own provider-routing accepts.

**Provider prefix.** crawl4ai's own default is `DEFAULT_PROVIDER = "openai/gpt-4o"`
(`config.py:7`), and its docstring for the deprecated `provider` kwarg states the format
explicitly: `"It follows the format <provider_name>/<model_name>, e.g., 'ollama/llama3.3'"`
(`extraction_strategy.py:594`). LiteLLM's own OpenAI-compatible-server doc
(<https://docs.litellm.ai/docs/providers/openai_compatible>) confirms the same convention for
a self-hosted server: use the `openai/` prefix followed by the model name (`model="openai/mistral"`
in their example), with the actual endpoint supplied via `base_url`/`api_base`, not baked into
the provider string. For this repo: **`"openai/google/gemma-4-e2b"`** — litellm only strips the
first `/`-delimited segment (`openai`) as the routing key and forwards the remainder
(`google/gemma-4-e2b`) verbatim as the `model` field in the JSON payload, which is exactly what
`agents/local_agent.py`'s own hardcoded default model string already is.

**`base_url`.** LiteLLM's doc is explicit that its OpenAI-compatible path should **not** have
`/v1` appended manually ("Do NOT add anything additional to the base url e.g. `/v1/embedding`.
LiteLLM uses the openai-client to make these calls, and that automatically adds the relevant
endpoints"), but the same page immediately caveats that some proxies need it back: "If you see
`Not Found Error` when testing make sure your `api_base` has the `/v1` postfix. Example:
`http://vllm-endpoint.xyz/v1`." The rule to apply: take whatever `LOCAL_API_URL` actually
resolves to in this repo's `.env` (the deployed endpoint is the Tailscale tunnel, not
`agents/local_agent.py`'s hardcoded LAN-IP fallback — see correction at the top of this doc) and
strip its trailing `/chat/completions`, keeping the `/v1` root — litellm's OpenAI client appends
`/chat/completions` itself, matching the same endpoint `local_agent.py` posts to directly.

**`api_token`.** `LLMConfig.__init__` (`async_configs.py:2217-2289`, trusted/non-untrusted
path) only reads `os.getenv(DEFAULT_PROVIDER_API_KEY)` (i.e. `OPENAI_API_KEY`) when
`api_token` is falsy **and** the provider string doesn't match any key in
`PROVIDER_MODELS_PREFIXES` (`async_configs.py:2266-2278`); since `"openai/..."` *does* match
the `"openai"` prefix in that dict, an empty `api_token` resolves to
`PROVIDER_MODELS_PREFIXES["openai"]` = `os.getenv("OPENAI_API_KEY")` (`config.py:32-39`) rather
than silently rewriting the provider back to `DEFAULT_PROVIDER` — but that's still `None` in an
environment with no real OpenAI key configured, and litellm's OpenAI-compatible client path
requires a truthy `api_key`. **Correction:** the analysis above (and the placeholder-token
framing generally) only applies to an *unauthenticated* local server. This repo's actual
deployment is not one — the Tailscale tunnel in front of it requires a real bearer token
(`pragma.yaml`'s own comment: "requires `LOCAL_API_KEY` in `.env` for auth"). `agents/local_agent.py`'s
own `_headers()` already sends this token as `Authorization: Bearer <LOCAL_API_KEY>`, and
`LLMConfig.api_token` must carry that same real value, not `"not-needed"` or any other
placeholder — a placeholder would reach the server but fail auth outright. Recommended:
`api_token=os.getenv("LOCAL_API_KEY")` at call time.

**Recommended `LLMConfig`:**

```python
import os
from crawl4ai import LLMConfig

llm_config = LLMConfig(
    provider="openai/google/gemma-4-e2b",
    api_token=os.getenv("LOCAL_API_KEY"),   # real bearer token - the tunnel requires it, no placeholder
    base_url=os.getenv("LOCAL_API_URL", "").removesuffix("/chat/completions"),
    temperature=0.7,                        # match agents/local_agent.py's hardcoded value
)
```

## Question 2 — extraction schema/instruction shape for `DESCRIPTIVE_COMPONENT_FIELDS`

`LLMExtractionStrategy.__init__` defaults `extraction_type="schema"` (`extraction_strategy.py:561`)
and only falls back to block-splitting behavior if `schema` is left `None`
(`extraction_strategy.py:608-611,672-677`). Which prompt template gets used is decided in
`extract`/`aextract` (`extraction_strategy.py:667-680`, `:870-885`):

| `instruction` set? | `schema` set? | Prompt used | Output shape forced |
|---|---|---|---|
| no | no | `PROMPT_EXTRACT_BLOCKS` | `{"index", "tags", "content": [str,...]}` — fixed |
| yes | no | `PROMPT_EXTRACT_BLOCKS_WITH_INSTRUCTION` | same fixed `{"index","tags","content"}` shape, instruction only steers *which* text gets grouped into blocks, not the object's keys |
| yes/no | yes | `PROMPT_EXTRACT_SCHEMA_WITH_INSTRUCTION` | driven by the JSON schema in `SCHEMA` — this is the only template whose output shape is field-list-driven |

`PROMPT_EXTRACT_BLOCKS_WITH_INSTRUCTION` (`prompts.py:51-106`) is textually near-identical to
the no-instruction template — its instructions for "generate ONE semantic tag" and `"content": [str, ...]`
are unconditional, so an instruction cannot make it emit `tag`, `role`, `input_type`, etc. as
top-level keys. **Schema-based extraction is the only fit** for
`DESCRIPTIVE_COMPONENT_FIELDS`/`ComponentFacts`.

`PROMPT_EXTRACT_SCHEMA_WITH_INSTRUCTION` (`prompts.py:108-143`) interpolates `{SCHEMA}` via
`json.dumps(self.schema, indent=2)` (`extraction_strategy.py:673`) — `self.schema` is typed as
a plain `Dict`, not a Pydantic model instance, so pass a JSON-schema dict (e.g. from a Pydantic
model's `.model_json_schema()`, or hand-built). The template already tells the model: "Return
the extracted information as a list of JSON objects... Wrap the entire JSON list in
`<blocks>...</blocks>` XML tags," plus a "Quality Reflection"/"Quality Score" chain-of-thought
scaffold and an explicit "Avoid Common Mistakes" list (no `//`/`#` comments, close the
`</blocks>` tag, don't emit Python code instead of doing the task) — this is a fairly long,
densely-worded prompt for a weak model; the `<score>` tag it also asks for is never consumed by
the parser (only `<blocks>` is extracted via `extract_xml_data(["blocks"], content)`,
`extraction_strategy.py:737`), so it's pure prompt overhead for this model and a candidate for
a project-side shortened variant of the same template in a future implementation ticket — noted
here as a risk, not something to fix in this research pass.

A JSON-schema dict matching the confirmed field list, one component per array item:

```python
component_schema = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            # DESCRIPTIVE_COMPONENT_FIELDS
            "tag": {"type": "string"},
            "text": {"type": "string"},
            "role": {"type": "string"},
            "input_type": {"type": "string"},
            "visible": {"type": "boolean"},
            "layer": {"type": "string"},
            "component_type": {"type": "string"},
            # ComponentFacts fields minus element_id
            "css_class": {"type": "string"},
            "href": {"type": "string"},
            "placeholder": {"type": "string"},
            "label": {"type": "string"},
            "name": {"type": "string"},
            "disabled": {"type": "boolean"},
            "required": {"type": "boolean"},
            "pattern": {"type": "string"},
            "min": {"type": "string"},
            "max": {"type": "string"},
            "minlength": {"type": "string"},
            "maxlength": {"type": "string"},
            "step": {"type": "string"},
            "form": {"type": "string"},
            "color": {"type": "string"},
            "background_color": {"type": "string"},
            "font_size": {"type": "string"},
            "font_weight": {"type": "string"},
            "display": {"type": "string"},
            "position": {"type": "string"},
            "border_radius": {"type": "string"},
            "border_color": {"type": "string"},
            "border_width": {"type": "string"},
            "box_shadow": {"type": "string"},
        },
        "required": ["tag", "text", "role", "component_type"],
    },
}

LLMExtractionStrategy(
    llm_config=llm_config,
    schema=component_schema,
    extraction_type="schema",
    instruction=(
        "Extract every visible interactive or content-bearing UI component from this page. "
        "For each component return the fields defined in the schema; use an empty string "
        "for any field that does not apply, and omit no keys."
    ),
)
```

30 fields on one object is itself a risk for a 2B/4B-class model — a future implementation
ticket may need to split extraction into multiple passes (e.g. structural fields first,
style/`ComponentFacts` fields second) if single-pass accuracy is poor; that split is out of
scope for this research ticket but worth flagging for #254/#255/#256.

## Question 3 — chunking strategy and threshold settings

Two independent chunking layers exist in the installed source, confirmed by tracing
`AsyncWebCrawler`'s extraction path (`async_webcrawler.py:911-937`):

1. **Pre-chunker** (`CrawlerRunConfig.chunking_strategy`, default `RegexChunking()` —
   `async_configs.py:1591,1865-1866`): runs once per page, *before* the extraction strategy
   sees anything. `async_webcrawler.py:921-927` shows this pre-chunker is only used when
   `input_format` resolves to `"markdown"`/`"fit_markdown"`; for `"html"`, `"cleaned_html"`, or
   `"fit_html"` content formats, the pre-chunker is **overridden to `IdentityChunking()`
   unconditionally** — i.e. the entire page becomes one chunk regardless of
   `chunking_strategy`, `chunk_token_threshold`, or page size. For a small local model with a
   limited context window, `input_format="html"` (or its cleaned/fit variants) is a direct risk
   of exceeding context on any non-trivial page — **use `input_format="markdown"`** (the
   `LLMExtractionStrategy` default, `extraction_strategy.py:566,589`) to keep the pre-chunker
   active.
2. **Extraction-time re-merge** (`LLMExtractionStrategy._merge` → `utils.merge_chunks`,
   `extraction_strategy.py:774-802`): every pre-chunked section (regardless of which
   `ChunkingStrategy` produced it) is re-tokenized by whitespace splitting and re-grouped into
   chunks of `chunk_token_threshold` tokens (default `2**11` = 2048, `config.py:43`) with
   `overlap = int(chunk_token_threshold * overlap_rate)` overlapping tokens (default
   `overlap_rate=0.1`, `config.py:44`) using `word_token_rate` (default `1.3`, `config.py:45`)
   to convert word counts to an approximate token count. **This second stage is what actually
   controls per-LLM-call size** — the pre-chunker's only real effect is *where* the text gets
   split before re-grouping (paragraph boundaries vs. words vs. sentences), not the final chunk
   size sent to the model.

Given that, `SlidingWindowChunking` (`chunking_strategy.py:174-211`) is a poor choice as the
*pre-chunker* for a weak model: by construction (`step < window_size` in the typical config) it
produces chunks that **overlap each other by design** — the same words appear in multiple
`sections` list entries *before* `merge_chunks` even runs, so redundant content gets fed into
multiple downstream LLM calls, wasting the model's already-limited context and increasing the
odds of duplicate/conflicting extracted objects across chunks. The default `RegexChunking()`
(splits on `\n\n`, `chunking_strategy.py:38-61`) produces non-overlapping paragraph-level
segments with no built-in redundancy — the safer default to leave alone; `merge_chunks`'s own
`overlap_rate` parameter is already crawl4ai's intended mechanism for controlled, tunable
overlap, making a separately-overlapping pre-chunker doubly redundant.

Recommended settings for `gemma-4-e2b` behind a small local context window:

```python
LLMExtractionStrategy(
    llm_config=llm_config,
    schema=component_schema,
    input_format="markdown",       # keeps RegexChunking() pre-chunker active (not IdentityChunking)
    apply_chunking=True,
    chunk_token_threshold=512,     # well below the 2048 default; smaller prompt = fewer malformed outputs
    overlap_rate=0.0,              # no manual overlap need; RegexChunking already avoids duplication
    force_json_response=False,     # local server has no JSON mode — see Question 1/4
)
```

`docs.crawl4ai.com/extraction/chunking/` lists the same chunking classes found in source
(regex, sentence/NLP, topic-segmentation, fixed-length-word, sliding-window) but — confirmed by
direct fetch — offers no guidance specific to small/local models or malformed-JSON risk; the
reasoning above is derived from the source's actual re-merge mechanics, not from any documented
recommendation.

## Question 4 — malformed-JSON handling, and whether it's sufficient here

No JSON-repair library and no retry-on-malformed-output exist anywhere in the installed
`crawl4ai==0.9.2` source. Traced end to end:

1. **Happy path** (`extraction_strategy.py:715-738`, sync; `:918-937`, async): with
   `force_json_response=False` (recommended, see Question 1), the response content is passed to
   `extract_xml_data(["blocks"], content)` (`utils.py:1709-1739`), which regex-matches
   `<blocks>...</blocks>` and — if the tag appears more than once — **keeps only the longest
   match** (`utils.py:1734`, `max(matches, key=len)`), then `json.loads()`s that string
   directly. There is no schema validation against the `schema` dict that was sent — whatever
   JSON shape comes back is accepted as-is (Question 2's `required` keys are advisory to the
   model only, not enforced by crawl4ai).
2. **Failure path** (`extraction_strategy.py:742-749`, sync; `:941-948`, async): any exception
   in the happy path (missing `<blocks>` tag, `json.JSONDecodeError`, etc.) is caught, and the
   **raw** response content is handed to `split_and_parse_json_objects` (`utils.py:707-749`) —
   a brace-depth counter that finds every top-level `{...}` span in the string and tries
   `json.loads()` on each independently. Segments that parse are kept as extracted objects;
   segments that don't are concatenated into `unparsed_segments` and appended as **one single**
   `{"index": 0, "error": True, "tags": ["error"], "content": unparsed}` block
   (`extraction_strategy.py:744-749`). This is a best-effort salvage, not a repair — it never
   rewrites malformed JSON (no trailing-comma fixup, no quote-matching, no
   `json_repair`/`json5`/`dirtyjson` dependency anywhere in `requirements` or imports), and it
   never re-calls the LLM to ask for a corrected response.
3. **The only retry loop in this path** is `perform_completion_with_backoff`/
   `aperform_completion_with_backoff` (`utils.py:1742-1834`), and it retries exclusively on
   `litellm.exceptions.RateLimitError` with exponential backoff
   (`base_delay`/`max_attempts`/`exponential_factor`, all configurable on `LLMConfig`,
   `async_configs.py:2229-2231,2257-2259`) — a malformed-JSON response is not an exception at
   the litellm/HTTP layer at all (the call succeeded; the *content* is just bad), so this retry
   path never triggers for it.
4. A hard failure anywhere in `extract`/`aextract` (network error, `response.usage` missing,
   etc.) is caught by the outer `try/except` and turned into a single
   `{"index": ix, "error": True, "tags": ["error"], "content": str(e)}` block per chunk
   (`extraction_strategy.py:761-772`, `:960-970`) — again, no retry of the LLM call itself
   beyond the rate-limit backoff.

**Sufficiency for `gemma-4-e2b`:** the brace-depth salvage is genuinely useful — a chunk where
the model got 3 of 5 objects right and mangled the last one still yields the 3 good objects
instead of discarding the whole chunk — but it has no mechanism to *recover* the dropped
objects, and it silently accepts any JSON shape that happens to parse without checking it
against the schema that was requested. For a model with a **high** malformed-JSON rate (no
JSON mode, weak instruction-following, per the ticket's framing), this project should plan a
project-side wrapper around `LLMExtractionStrategy` for a future implementation ticket
(#254/#255/#256) that at minimum: (a) inspects the returned block list for `error: True`
entries or objects missing required schema keys, and (b) re-issues a corrective follow-up call
for just that chunk (e.g. "your previous response was not valid JSON / was missing field X,
here is the schema again, please retry") rather than accepting crawl4ai's single silent
`error` block as the final answer for that chunk. crawl4ai's behavior is a reasonable floor for
a well-behaved cloud model; it is not built to compensate for a small local model's higher
failure rate.

## Corrections / gaps vs. what a naive reading of the docs would suggest

- LiteLLM's own `openai_compatible` doc's "do NOT add `/v1`" guidance is directly contradicted
  by its own follow-up note for exactly this project's situation (a custom local server) — the
  doc itself hedges rather than giving one unconditional rule; the recommendation above follows
  the hedge (`.../v1`, no further suffix) because it matches `agents/local_agent.py`'s already
  confirmed working endpoint shape.
- `docs.crawl4ai.com`'s LLM-extraction page frames instruction-based extraction as a real
  alternative to schema-based ("Uses freeform text or smaller JSON structures guided by your
  `instruction` parameter") without flagging that the installed source's instruction-only
  prompt template hardcodes an unrelated `{index, tags, content}` shape — confirmed only by
  reading `prompts.py` directly, not stated in the docs at all.
- `docs.crawl4ai.com/extraction/chunking/` documents the chunking-strategy classes as if they
  were the primary lever for LLM chunk size; source tracing shows `chunk_token_threshold`/
  `overlap_rate` on `LLMExtractionStrategy` (a separate re-merge stage) actually dominates,
  and `input_format="html"` silently bypasses the configured `chunking_strategy` entirely — none
  of this interaction is documented on that page.
