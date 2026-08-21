# Research: reusing the local-HTTP-model client for text-proximity scoring (#128)

> Research child of #127 (component matching: embedding-based dedup and family grouping).
> Ticket: #128, "Local HTTP model for text-proximity scoring." Blocks #131.

## Summary

Yes, this repo already runs a local HTTP-served model, and its client lives at
`agents/local_agent.py::LocalAgent`. It's a synchronous `requests.post` call to an
OpenAI-compatible **chat completions** endpoint (`/v1/chat/completions`) — no async client
anywhere in the codebase. `component_family_narrator.py` and `component_clustering.py` call it
exactly once per component *family* (not per pair, not per component), which is why a several-
hundred-millisecond-to-several-second round trip per call is acceptable there. That call pattern
cannot be reused as-is for text-proximity scoring: `component_family.py`'s existing pairwise
clustering (`_cluster_bucket`) is `O(n²)` comparisons *within* a same-`(tag, component_type)`
bucket, done in-process with plain Python set arithmetic (Jaccard similarity) and zero I/O. Given
#127's stated design — a deterministic feature-vector similarity where text-proximity is one input
signal, computed at cluster time — routing that signal through a chat-completions endpoint would
turn a return matched pattern into `O(n²)` blocking HTTP requests. The existing chat-completions
client and its config (`LOCAL_API_URL`/`LOCAL_MODEL`/`LOCAL_API_KEY`/`LOCAL_TIMEOUT`) are the right
building block to reuse — the local server (LM Studio in this repo's actual `.env.example`/
`pragma.yaml`) almost certainly also exposes an OpenAI-compatible `/v1/embeddings` endpoint — but
the *call shape* has to change: an embeddings endpoint returning vectors that get compared with
cosine/dot-product locally, not a chat prompt asking the model to judge similarity in prose. A new,
narrow client (or a thin embeddings-specific method) is needed; the existing `LocalAgent.generate()`
chat-completions call is not directly reusable for this signal.

## What already exists: the local HTTP model client

### Client code

`agents/local_agent.py` (full file read):

```python
# agents/local_agent.py:1-11
"""Local agent implementation for Pragma, connecting to a local model API."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import requests

from core.interfaces import Agent
from core.registry import AGENT_REGISTRY
```

Config dataclass, `LOCAL_*` env vars:

```python
# agents/local_agent.py:14-39
@dataclass
class LocalConfig:
    base_url: Optional[str] = None
    model: Optional[str] = None
    timeout: int = 300
    api_key: Optional[str] = None
    max_tokens: Optional[int] = None

    @classmethod
    def from_env(cls) -> "LocalConfig":
        env_timeout = os.getenv("LOCAL_TIMEOUT")
        env_max_tokens = os.getenv("LOCAL_MAX_TOKENS")
        return cls(
            base_url=os.getenv("LOCAL_API_URL"),
            model=os.getenv("LOCAL_MODEL"),
            timeout=int(env_timeout) if env_timeout else 300,
            api_key=os.getenv("LOCAL_API_KEY"),
            max_tokens=int(env_max_tokens) if env_max_tokens else None,
        )
```

Constructor default endpoint and model (falls back to these only if neither an explicit arg nor an
env var supplies them):

```python
# agents/local_agent.py:56-65
config = LocalConfig.from_env()
self.base_url = base_url or config.base_url or "http://192.168.68.76:1234/v1/chat/completions"
self.model = model or config.model or "google/gemma-4-e2b"
self.timeout = timeout or config.timeout
self.api_key = api_key or config.api_key
self.max_tokens = max_tokens if max_tokens is not None else config.max_tokens
```

The actual call — a synchronous, blocking `requests.post` against a chat-completions endpoint:

```python
# agents/local_agent.py:99-115
def _generate_request(self, prompt: str, system_instruction: Optional[str]) -> str:
    """Internal helper to make the API request."""
    payload = self._build_payload(prompt, system_instruction)

    try:
        resp = requests.post(
            self.base_url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Local API Error ({resp.status_code}): {resp.text}")
        return self._parse_response(resp.json())

    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Local API request failed: {exc}") from exc
```

Payload shape confirms this is a **chat/completion**-style request, not an embeddings request —
`messages`, `temperature`, optional `max_tokens`, and the response is parsed out of
`choices[0].message.content`:

```python
# agents/local_agent.py:117-131
def _build_payload(self, prompt: str, system_instruction: Optional[str]) -> dict[str, Any]:
    """Build the OpenAI-compatible request payload."""
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": self.model,
        "messages": messages,
        "temperature": 0.7,
    }
    if self.max_tokens is not None:
        payload["max_tokens"] = self.max_tokens
    return payload
```

```python
# agents/local_agent.py:133-144
def _parse_response(self, data: dict[str, Any]) -> str:
    """Extract content from OpenAI-compatible response format."""
    try:
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"Unexpected API response format: {data}")
        self._raise_if_truncated(choices[0])
        content = choices[0].get("message", {}).get("content", "")
        return content.strip()
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Failed to parse Local API response: {exc}") from exc
```

`core/interfaces.py:41-47` defines the `Agent` ABC this implements — one abstract method,
`generate(prompt, system_instruction=None) -> str`, plain text in/out, no vector or embedding
return type anywhere on the interface:

```python
# core/interfaces.py:41-47
class Agent(ABC):
    """Interface for AI agent backends."""

    @abstractmethod
    def generate(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Return text generated by an LLM or agent backend."""
        raise NotImplementedError
```

`agents/mock_agent.py:12-27` (`MockAgent`) is the only other `Agent` implementation in the repo —
a static, heuristic stand-in for tests, not another HTTP path. No `httpx`, `aiohttp`, or
`async def` appears anywhere under `agents/` or in `core/interfaces.py`; `requests` (synchronous)
is the only HTTP client library this agent layer uses.

### Config keys (env vars, base URL, model, timeout)

From `.env.example:8-28`:

```
# --- local (LM Studio / any OpenAI-compatible server) ---
LOCAL_API_URL=http://localhost:1234/v1/chat/completions
LOCAL_MODEL=google/gemma-4-e2b
LOCAL_API_KEY=
LOCAL_TIMEOUT=300
LOCAL_MAX_TOKENS=
```

`pragma.yaml:31-45` shows the same settings can also be set under `agents.local` in the project's
YAML config, and that YAML wins over the `.env` value when both are set (documented explicitly
in-file):

```yaml
agents:
  local:
    base_url: https://local.tailb3c4a4.ts.net/v1/chat/completions
    # model: intentionally left unset here ...
    timeout: 1800
    max_tokens: 8192
```

So the full key set is: `LOCAL_API_URL`/`agents.local.base_url`,
`LOCAL_MODEL`/`agents.local.model`, `LOCAL_API_KEY` (bearer auth, env-only — deliberately kept out
of the committed YAML per `.env.example:5-6`), `LOCAL_TIMEOUT`/`agents.local.timeout`, and
`LOCAL_MAX_TOKENS`/`agents.local.max_tokens`. `AGENT_PROVIDER=local` (also in `.env.example`)
selects `LocalAgent` via `core/registry.py`'s `AGENT_REGISTRY`.

Both of the two real deployments recorded in this repo — `.env.example`'s default
(`localhost:1234`, i.e. LM Studio's own default local port) and `pragma.yaml`'s actual configured
value (a Tailscale-tunneled hostname, `https://local.tailb3c4a4.ts.net/...`, reaching a model on a
separate physical machine, per `pragma.yaml:32-34`'s comment) — point at `/v1/chat/completions`.
Both are genuinely **local/self-hosted models** (LM Studio, reached directly or through a personal
Tailscale tunnel), not a hosted third-party API like OpenAI's public endpoint — confirmed by
`ARCHITECTURE.md:345`'s summary line and the LM Studio-specific docstring in `local_agent.py:44`.

## The call pattern the narration step actually uses

`generators/component_family_narrator.py::narrate_family_purposes` calls `agent.generate()` once
per **family**, not per component and not per pair:

```python
# generators/component_family_narrator.py (excerpt, narrate_family_purposes)
try:
    purpose = agent.generate(prompt, system_instruction=PURPOSE_SYSTEM_INSTRUCTION).strip()
except Exception:  # noqa: BLE001 - degrade this one family, not the whole pass
    purpose = ""
```

This runs inside a plain `for family, texts in zip(families, texts_per_family):` loop — sequential,
blocking calls, one after another, with a `print(f"  family {family_number}/{total_calls}: ...")`
progress line before each call (the module docstring calls this "the slowest step between the end
of the crawl and the first written document"). It is deliberately cheap in *call count*: families
already cap prompt content at 20 deduplicated texts (`_MAX_TEXTS_PER_FAMILY`), and a
content-unchanged family reuses its prior purpose instead of re-calling the model
(`known_purposes`/`family_signature`, `component_family_narrator.py:39-58` and
`analysis/component_clustering.py:64-72`). The number of calls scales with the number of *distinct
inferred families* on a site, not with the number of raw components or component pairs — typically
a small number even on a large crawl.

`analysis/component_clustering.py::apply_component_families` is the sole caller
(`component_clustering.py:73`: `families = narrate_family_purposes(agent, families, member_texts, known_purposes)`),
and it invokes this whole pipeline **once per site, post-hoc**, after
`build_component_families` has already finished clustering (`component_clustering.py:60-62`):

```python
# analysis/component_clustering.py:60-63
components = flat_component_ledger(graph_store)
families = build_component_families(components)
print(f"Grouped {len(components)} components into {len(families)} families.")
member_texts = {(c["page_url"], c["path"]): c.get("text", "") for c in components}
```

Critically, the *clustering itself* — the part that does pairwise comparison — never calls the
model at all. `generators/component_family.py::_cluster_bucket` does the pairwise work, in-process,
with a plain nested loop over Jaccard similarity of `css_class` token sets:

```python
# generators/component_family.py:167-172
token_sets = [_class_tokens(m.get("css_class", "")) for m in members]
uf = _UnionFind(len(members))
for i in range(len(members)):
    for j in range(i + 1, len(members)):
        if _similarity(token_sets[i], token_sets[j]) >= _SIMILARITY_THRESHOLD:
            uf.union(i, j)
```

This is explicitly `O(n²)` pairs within each `(tag, component_type)` bucket (module docstring at
`component_family.py:149-166` documents the same complexity in prose), and it's cheap only because
each comparison is a local set-intersection, not a network call. The LLM only enters the pipeline
*after* clustering has already produced families — one call per resulting group, never one call per
raw pairwise comparison.

## Reasoning: narration call pattern vs. what per-pair text-proximity scoring needs

#127's design (per the issue body) replaces `component_family.py`'s Jaccard clustering with "a
deterministic, hand-calculated feature-vector similarity over `Component` fields," with
text-proximity between `text`/`label` values as one signal among several, computed **at cluster
time** — i.e., during the same kind of pairwise (or near-pairwise, via bucketing/union-find)
comparison `_cluster_bucket` already performs today, just with a richer distance function.

The narration step's cheapness comes specifically from being *post-clustering* and
*per-group*: it runs after grouping has already collapsed N components down to a handful of
families, so the LLM is asked one question per family, not per component pair. Text-proximity
scoring is the opposite shape by construction — it's an input to the grouping decision itself, so
it necessarily runs before/during clustering, at the same cardinality as
`_cluster_bucket`'s existing double loop: up to `O(n²)` comparisons per `(tag, component_type)`
bucket (bounded some by bucketing, same as today, but still quadratic within a bucket on a
site with many similar buttons/links).

`LocalAgent.generate()` is a synchronous, single-request-per-call, chat-completions round trip with
a **300-second default timeout** (`LocalConfig.timeout`, `.env.example:20`) and this repo's real
deployment sets it to **1800 seconds** (`pragma.yaml:41`, because the tunneled model is slow).
Issuing one such call per component pair would turn a bucket of, say, 50 similar buttons (1225
pairs) into up to 1225 sequential blocking HTTP requests before clustering can even produce one
family — a pattern this codebase has already flagged as a cost/timeout risk once for the
*narration* step alone (see `wiki/local-and-small-model-constraints.md:109-110` and
`research/plan-progreso-en-terminal.md`, both about the same local model's latency under far lighter
call volume: one call per family, not per pair). Nothing in the current code path amortizes or
batches chat-completions calls across multiple comparisons; `_build_payload` always builds a single
`messages` list for one `prompt`.

## Would the same client/endpoint work, or is a different endpoint needed?

The `/v1/chat/completions` endpoint `LocalAgent` calls is the wrong shape for this signal on two
independent grounds:

1. **Call cardinality.** A chat-completions call is priced (in latency) for "ask the model to
   reason and produce text," which is appropriate once per family (narration) but not appropriate
   `O(n²)` times per bucket (proximity scoring at cluster time).
2. **Response shape.** Chat completions return free-form text; a numeric similarity score would
   have to be extracted from a prompted-for text answer (e.g. "reply with a number 0-1"), which is
   fragile compared to an embeddings endpoint that returns a fixed-length float vector directly
   comparable via cosine similarity — and which fits naturally with #127's already-decided plan to
   store vectors as native Kùzu `ARRAY` columns with an HNSW index (per #127's issue body), i.e.
   the target architecture is already vector-shaped, not text-answer-shaped.

An OpenAI-compatible embeddings endpoint (conventionally `/v1/embeddings` on the same LM
Studio/Tailscale-tunneled server this repo already points `LOCAL_API_URL` at) is the natural fit:
one HTTP call per distinct `text`/`label` string to get a vector (cacheable/dedupable the same way
`narrate_family_purposes` already dedupes texts before narrating, `component_family_narrator.py:
64-71`), after which every pairwise comparison the clustering step needs becomes a local
vector-distance computation — no HTTP call per pair at all, matching `_cluster_bucket`'s existing
in-process cost profile. This repo's code does not currently define or call any embeddings
endpoint anywhere; a grep for `embedding`, `/v1/embeddings`, or a second `Agent`-like interface
returning vectors turned up nothing outside this ticket's own issue text.

## Recommendation

**Needs new tooling, but reuses the existing config surface.** Concretely:

- Do not route per-pair text-proximity scoring through `LocalAgent.generate()`
  (`/v1/chat/completions`) — the call pattern (`O(n²)` per bucket, at cluster time) does not match
  what that endpoint/method were built for (`O(families)` calls, post-clustering, one narrated
  sentence each), and chat-completions responses aren't a clean source for numeric similarity
  scores.
- Reuse the existing `LOCAL_API_URL`/`LOCAL_MODEL`/`LOCAL_API_KEY`/`LOCAL_TIMEOUT` config keys and
  `pragma.yaml`'s `agents.local` precedence rules (same server, same auth, same env-vs-YAML
  override behavior already documented and battle-tested) — no new config plumbing needed, just a
  second endpoint path off the same base host, or a sibling `LOCAL_EMBEDDINGS_URL`-style key if the
  embeddings route differs from the chat-completions one on the target server.
- Add a small, separate client (or a second method alongside `LocalAgent`, not a new abstract
  method forced onto every `Agent` implementation like `MockAgent`) that calls an
  **embeddings-style endpoint once per distinct text string** (deduplicated up front, the same
  discipline `component_family_narrator.py` already applies to narration texts), caches the
  resulting vectors, and lets `component_family.py`'s clustering step compute all pairwise
  similarities locally via cosine/dot-product on those vectors — keeping the `_cluster_bucket`-style
  loop's actual network-call count at `O(distinct texts)`, not `O(pairs)`.
- Confirm with the actual local model deployment (LM Studio's own docs, not guessed) whether the
  loaded model (`google/gemma-4-e2b` in `.env.example`, `qwen2.5-coder-7b-instruct` referenced in
  `pragma.yaml`'s comments) exposes a real embeddings route, or whether a separate,
  embeddings-purpose-built local model needs to be loaded alongside/instead of the chat model —
  this repo's own source does not settle that; it settles only that no embeddings call exists here
  yet.

## Files read for this research

- `agents/local_agent.py` (full)
- `agents/mock_agent.py` (full)
- `core/interfaces.py:41-47` (`Agent` ABC)
- `generators/component_family_narrator.py` (full)
- `generators/component_family.py` (full)
- `analysis/component_clustering.py` (full)
- `.env.example:1-28`
- `pragma.yaml:1-46`
- `ARCHITECTURE.md:345`
- `wiki/local-and-small-model-constraints.md` (grep hits, lines 50/56/109/110)
- `research/plan-progreso-en-terminal.md` (grep hit, line 42)
- `research/diagnostico-corrida-sin-fin.md` (grep hit, line 168)
- GitHub issues #127 and #128 (`gh issue view`), for the map's stated architecture and this
  ticket's exact question
