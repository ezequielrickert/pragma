# Research: RAG over Neo4j, for a future Q&A/chat feature (not a fix for today's bug)

> This is forward-looking research, not a durable lesson from a bug this project already hit -
> that's why it lives here in `research/` instead of `wiki/`. It was produced investigating a
> proposed fix for the `max_tokens` truncation crash in `GraphPRDSynthesizer.synthesize()`
> (2026-08-10) - that investigation concluded RAG was the wrong tool for *that* problem (see
> `docs/explicativos/` for the incident, and the actual fix landed as bounded map-reduce batching
> in `generators/graph_prd_synthesizer.py`). This doc preserves the RAG research itself, since
> it's genuinely useful if a different feature - ad-hoc Q&A/chat over a crawled site's data - is
> ever built.

## The question that was actually asked

> Could a RAG system - an HTTP service on this machine, called by a local LLM running on a
> dedicated PC, built on the existing Neo4j graph instead of a fresh vector database - help with
> local-model context limits?

## Why RAG is the wrong tool for documentation synthesis specifically

RAG's whole value proposition is *selective* retrieval: given a large corpus and a specific
question, fetch only the most relevant few chunks and answer from those, deliberately leaving most
of the corpus out. That's the correct behavior for Q&A, and the wrong behavior for **comprehensive
coverage** tasks - a "document everything the crawl found" task needs the *opposite* property:
every page needs to end up mentioned somewhere, and a retrieval step that decides some pages aren't
"relevant enough" to the fetch produces a document with real content silently missing, not a faster
version of the same document.

The standard, correct pattern for "corpus exceeds one context window, but the output must cover
all of it" is **map-reduce summarization** - split the corpus into bounded chunks, summarize each
independently (map), then combine the summaries (reduce) - not retrieval. This is exactly the
shape `GraphPRDSynthesizer` now uses.

Separately: the specific error this investigation started from (`finish_reason: "length"`) is an
**output** token-budget limit (`max_tokens`), not an input context-window limit. RAG only ever
shrinks the input side of a request. Even a hypothetically perfect retrieval step in front of a
"write the entire document in one completion" call would still need that one completion to cover
everything retrieval selected - it doesn't reduce how long the model's answer needs to be.

## Neo4j as a RAG backend, if this is ever built for a real Q&A use case

**Verdict: viable, and reuses infrastructure this project already runs - genuinely worth doing over
standing up a separate vector database, when the day comes.**

- This project's Neo4j is version **5.24-community** (`docker-compose.yml`), well past the **5.11**
  minimum for native vector indexes - no GenAI plugin, no separate vector store needed.
  [Neo4j's vector index docs](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
  confirm 5.11 as the baseline, 5.13 recommended for the full tutorial-covered feature set, 5.18+
  for advanced metadata filtering (in-index filter predicates rather than post-hoc brute-force
  scanning) - all comfortably below 5.24.
- As of Neo4j 2026.01+, native Cypher `SEARCH` syntax makes vector queries first-class (no
  procedure-call boilerplate), and filtered vector search is GA since 2026.02 - see
  [Neo4j's vector-search-with-filters post](https://neo4j.com/blog/genai/vector-search-with-filters-in-neo4j-v2026-01-preview/).
- **Nothing in this codebase does this today.** Confirmed by direct search: zero hits for
  `chunk`/`embedding`/`vector`/`rag` anywhere in `src/`. `Neo4jGraphStore`
  (`database/neo4j_graph_store.py`) has three plain B-tree property indexes (on `site`) and no
  full-text or vector index at all. Building this means the whole pipeline from scratch: choosing
  an embedding model, a chunking strategy for `Component.text`/`TextContent.text` (currently
  unbounded-length raw extracted text - would need real chunking, unlike `Page.description` which
  is already truncated to 300 chars at extraction time), an ingestion step that writes vectors
  alongside existing nodes, and the actual `CREATE VECTOR INDEX` + query-time `SEARCH`/similarity
  call. None of that exists as a stub or TODO anywhere in this repo currently.
- **Graph-shaped retrieval (multi-hop, relationship-aware) vs. pure vector similarity** is a real,
  separate consideration if this is ever built: current industry framing (2026) contrasts "Graph
  RAG" (traverses real relationships - e.g. "what pages does this component's interaction lead
  to," which `NAVIGATED_TO`/`DISCOVERED_LINK` edges already encode) against pure vector similarity,
  which can't follow multi-hop reasoning at all and is prone to ambiguity collisions (e.g.
  conflating unrelated things that happen to embed similarly). For a crawled-site knowledge base
  where "how do I get from the cart to checkout" is a graph-traversal question, not a
  similarity-search question, this project's existing edge/relationship data is a genuine asset a
  pure-vector RAG system would have to reconstruct from scratch. See
  [Neo4j's knowledge-graph-vs-vector-RAG comparison](https://neo4j.com/blog/developer/knowledge-graph-vs-vector-rag/)
  and [Instaclustr's Graph RAG vs vector RAG overview](https://www.instaclustr.com/education/retrieval-augmented-generation/graph-rag-vs-vector-rag-3-differences-pros-and-cons-and-how-to-choose/).

## The tool-calling question: pre-retrieval step vs. model-invoked tool

This is the one decision that matters most if this is ever built, and it's specific to this
project's current architecture, not a generic RAG concern.

**Every LLM call in this codebase today is a single flat-string completion.** `Agent.generate(prompt,
system_instruction) -> str` is the entire interface (`core/interfaces.py`). There is no
tool-calling ladder to reuse - `LocalAgent`'s own docstring
(`agents/local_agent.py`) states plainly that the native OpenAI-style tool-calling support that
used to exist was **deliberately removed** post-crawl4ai-migration, because the per-step structured
action schema it existed for no longer exists. Reintroducing tool-calling to let the model *decide*
when to query the RAG backend would mean rebuilding that removed ladder from scratch.

This project's own `wiki/tool-calling-and-execution-layers.md` already documents a real failure
mode directly on point: a local OpenAI-compatible server silently accepted a `tools` request
parameter but its chat template ignored it, returning plain text with no error at all - a fallback
ladder (native → JSON-in-text → legacy verb grammar) is the prescribed defense, probed once and
cached per agent instance.

Current (2026) research on small/quantized local models specifically reinforces this risk:
- Sub-7B models show "low or zero tool invocation rates, confabulated responses in place of tool
  use, and catastrophic failure on multi-step tool chains," with factual-QA/tool mismatch rates
  measured at 26.5-54% across several open-weight 3B-8B models
  ([dev.to benchmark writeup](https://dev.to/anak_wannaphaschaiyong_11/why-small-llms-fail-at-tool-calling-the-shocking-discovery-from-our-llama-3b-benchmark-5lg)).
- Even where tool-calling nominally works, headline reliability is "90%+ well-formed calls on
  simple workloads; 80-90% end-to-end on multi-step real workflows after compounding selection and
  argument errors"
  ([Docker's local-LLM tool-calling evaluation](https://www.docker.com/blog/local-llm-tool-calling-a-practical-evaluation/)).
- Training/architecture matters more than raw size at this tier - "a 14B model that calls the right
  function every time beats a 70B model that gets it right only half the time" - but this project's
  configured local model (`google/gemma-4-e2b`, an ~2B-class model per its own name) sits well
  below even the 7B floor these benchmarks treat as a reliability cliff.

**Recommendation if this is ever built**: expose RAG as a **pre-retrieval step your own
orchestrator runs before building the prompt** - query Neo4j (vector and/or graph-traversal),
format the results into the prompt string, then one ordinary `agent.generate()` call - the exact
shape `GraphPRDSynthesizer` already uses today (gather data from `GraphStore` → build one prompt →
one `generate()` call). Never a model-invoked tool call, given the current model tier and the
absence of any fallback ladder to catch a silent tool-calling failure.

## The HTTP/network architecture itself is not a real risk

Worth noting explicitly, since it was part of the original question: a RAG service running on this
machine, called over HTTP by whatever process builds the prompt, is architecturally consistent with
what's already running. `LocalAgent` already talks to a remote model host over a Tailscale tunnel
(`https://local.tailb3c4a4.ts.net/v1/chat/completions`) today - adding a second HTTP hop (to a local
RAG endpoint, from whichever side ends up owning prompt construction) is not a new risk category for
this setup. The task-shape mismatch and tool-calling reliability points above are the real
considerations, not the transport.

## Summary

| Question | Answer |
|---|---|
| Would RAG fix the `max_tokens` truncation bug? | No - RAG shrinks input, the bug is an output-length limit. |
| Is RAG the right tool for comprehensive doc synthesis? | No - that's a map-reduce coverage task, not a selective-retrieval task. |
| Would Neo4j work as a RAG backend if built for a real Q&A feature later? | Yes - v5.24 supports native vector indexes with no plugin/separate DB needed, and its existing relationship data is a real asset over pure vector similarity for multi-hop questions. |
| Does anything need building for that today? | Yes, everything - chunking, embeddings, ingestion, vector index creation, and retrieval query logic all need to be built from scratch. |
| Should retrieval be a model-invoked tool or a pre-retrieval step? | Pre-retrieval step, always, at this model tier - `LocalAgent` has no tool-calling ladder today, and small local models are documented as unreliable at tool-calling. |

## Sources

- [Neo4j Cypher Manual: Vector Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Neo4j: Vector search with filters (2026.01 preview / 2026.02 GA)](https://neo4j.com/blog/genai/vector-search-with-filters-in-neo4j-v2026-01-preview/)
- [Neo4j: Knowledge graph vs. vector RAG - benchmarking and optimization levers](https://neo4j.com/blog/developer/knowledge-graph-vs-vector-rag/)
- [Instaclustr: Graph RAG vs vector RAG - differences, pros and cons](https://www.instaclustr.com/education/retrieval-augmented-generation/graph-rag-vs-vector-rag-3-differences-pros-and-cons-and-how-to-choose/)
- [Meilisearch: Knowledge graph vs. vector database for RAG](https://www.meilisearch.com/blog/knowledge-graph-vs-vector-database-for-rag)
- [Docker: Local LLM Tool Calling - A Practical Evaluation](https://www.docker.com/blog/local-llm-tool-calling-a-practical-evaluation/)
- [dev.to: Why Small LLMs Fail at Tool Calling - a Llama 3B benchmark](https://dev.to/anak_wannaphaschaiyong_11/why-small-llms-fail-at-tool-calling-the-shocking-discovery-from-our-llama-3b-benchmark-5lg)
- [Galileo.ai: Master LLM Summarization Strategies and their Implementations](https://galileo.ai/blog/llm-summarization-strategies)
- `wiki/tool-calling-and-execution-layers.md` (this repo) - native tool-calling degradation and the
  fallback-ladder pattern.
- `wiki/local-and-small-model-constraints.md` (this repo) - "cap what goes into every prompt,
  always" - the actual lesson that fixed today's bug.
