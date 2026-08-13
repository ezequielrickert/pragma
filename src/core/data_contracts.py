"""Plain data contracts shared across the Pragma micro-kernel - split out
of `interfaces.py` to keep that file under this project's file-size
threshold. Every name here is re-exported from `interfaces.py` (not
moved-and-forgotten), so every existing `from ..core.interfaces import
ComponentFacts` (etc.) import site keeps working unchanged - this file
holds the real definitions, `interfaces.py` just imports and re-exposes
them alongside `Agent`/`GraphStore`, the actual *interfaces* (as opposed
to plain data) that still live there.

Details: docs/dev/core/data_contracts.md#module
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class PageState:
    """Normalized snapshot of a crawled page (the Crawler -> orchestrator contract)."""

    url: str
    title: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    components: List[Dict[str, Any]] = field(default_factory=list)
    links: List[Dict[str, str]] = field(default_factory=list)
    # Short (~300 char) page summary; "" if the backend doesn't extract it.
    # Details: docs/dev/core/interfaces.md#pagestatedescription
    description: str = ""
    # Meaningful (xhr/fetch) requests triggered by the interaction, if any.
    # Details: docs/dev/core/interfaces.md#pagestatenetwork_requests
    network_requests: List[Dict[str, Any]] = field(default_factory=list)
    # Non-interactive prose, captured once per page visit alongside components.
    # Details: docs/dev/core/interfaces.md#pagestatetext_content
    text_content: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ComponentFacts:
    """DOM-attribute and computed-style facts about a discovered element,
    beyond the core identity/geometry `record_component` already took as
    named params. Grouped into one object rather than growing that method's
    own argument list further - see docs/dev/core/interfaces.md#componentfacts
    for which facts are here and, notably, which one (`value`) isn't and why.
    """

    css_class: str = ""
    element_id: str = ""
    href: str = ""
    placeholder: str = ""
    label: str = ""
    name: str = ""
    disabled: bool = False
    required: bool = False
    form: str = ""
    color: str = ""
    background_color: str = ""
    font_size: str = ""
    font_weight: str = ""
    display: str = ""
    position: str = ""


@dataclass(frozen=True)
class ComponentFamily:
    """One inferred reusable-component cluster (a "Button" pattern, a
    "combobox" pattern, ...) - a post-hoc, whole-site grouping of already-
    discovered Components by structural/visual similarity, computed by
    `src/generators/component_family.py::build_component_families` (that
    module's own docstring has the full algorithm - bucketed by `(tag,
    component_type)`, then clustered within each bucket by CSS-class
    similarity). Lives here (not in `generators/`) so `GraphStore` - a
    `core` module - can reference the type without `core` depending on
    `generators`, the reverse of this project's normal layering.

    Frozen + tuple fields (not list) so a `ComponentFamily` is hashable
    and safely comparable by value - callers (tests, in particular) can
    put one in a `set` or compare two family lists with plain `==`.

    Fields:
        tag: the raw HTML tag every member shares, e.g. `"button"`,
            `"input"`, `"a"`. See `component_family.label_for_tag` for
            how this becomes a Neo4j node label (`"button"` -> `Button`,
            `"a"` -> `Link`, etc.) - a related but separate mechanism
            from family grouping itself.
        component_type: the human-readable role label every member
            shares, e.g. `"button"`, `"submit button"`, `"checkbox"`,
            `"combobox (searchable dropdown)"` - the same value
            `component_classifier.classify_component_type` already
            computed for each component at crawl time. Two components
            with the same `tag` but different `component_type` are never
            in the same family, regardless of how similar their classes
            are.
        common_classes: the CSS classes *every* member has in common -
            sorted for a deterministic, human-readable summary of what
            the family visually shares (e.g. `("btn", "rounded")` for a
            primary/secondary button pair that differs only by its
            color-modifier class, which is correctly excluded here since
            not every member has it).
        member_paths: one `(page_url, path)` pair per member component -
            together, the two fields are exactly the identity key
            (`site` is implied by whichever call this came from)
            `GraphStore.record_component`/`get_component_states` use for
            a single `Component` node. Sorted for a deterministic order.
        purpose: one-sentence, human-readable description of what this
            pattern is typically used for (e.g. "confirms or submits an
            action"), or `""` if it was never narrated. `build_component_
            families` itself never sets this (clustering is pure/no-LLM,
            per that module's own docstring) - it's filled in afterward
            by `component_family_narrator.narrate_family_purposes`, an
            explicitly separate, impure step that needs an `Agent`.
    """

    tag: str
    component_type: str
    common_classes: Tuple[str, ...]
    member_paths: Tuple[Tuple[str, str], ...]
    purpose: str = ""


@dataclass(frozen=True)
class InferredRequest:
    """One distinct API endpoint's shape, inferred from every network
    request matching the same `(method, endpoint, query_params)` seen
    across a crawl - computed by `src/generators/request_family.py::
    build_inferred_requests`. Lives here (not in `generators/`) for the
    same layering reason as `ComponentFamily`.

    Frozen + tuple fields, same reasoning as `ComponentFamily`: hashable,
    safely comparable by value.

    Fields:
        method: the HTTP method every occurrence shared, e.g. `"GET"`,
            `"POST"` - uppercased. This is also the grouping key
            `GraphStore.record_inferred_requests` uses to create one
            `:RequestFamily` node per distinct method (a trivial groupby,
            unlike `ComponentFamily`'s similarity clustering - there's no
            algorithm to speak of, "GET" and "POST" are never the same
            family by definition).
        endpoint: `host/path`, with any opaque generated path segment
            (an order id, a session token) collapsed to `{id}` - the same
            heuristic (`utils.urls.is_opaque_token`) `route_shape` already
            applies to page URLs, applied here to API URLs for the
            analogous reason.
        query_params: sorted, deduplicated query-string parameter
            *names* only - e.g. `("order_id", "select")` - never the
            values a real query string carries (an order id, a share
            token), which is exactly the kind of per-instance data this
            whole feature deliberately never persists.
        body_shape: JSON-encoded structural shape of the request body
            (key names and value *types* only, e.g. `'{"order_id":
            "string"}'`) - see `network_filter._json_shape` for how a
            real value becomes just its type name. `""` if no request in
            this group ever had a body, or none of them had a
            JSON-parseable one.
        response_shape: same idea, for the response body. `""` under the
            same conditions.
        triggered_by: one `(page_url, path)` pair per `Component` whose
            interaction produced at least one request in this group -
            sorted for a deterministic order. A single endpoint hit by
            several different components (e.g. four separate "Agregar"
            buttons all calling the same `participant_selections`
            endpoint) lists every one of them, not just the first.
        loaded_by: page urls whose own *load* fired this request, with no
            component involved - a SPA fetching what it needs to render.
            Kept separate from `triggered_by` rather than folded in with a
            blank path: "this endpoint is called when you open /orders" and
            "this endpoint is called when you click Save" are different
            facts, and an OpenAPI description that conflates them is
            wrong about how the application works.
        status_codes: every distinct HTTP status this endpoint answered
            with across the crawl, sorted. This is what an OpenAPI
            `responses:` block is built from - without it the block is
            invention.
        latencies_ms: every measured request-to-response time, sorted.
            Relative signal only (see `network_filter._latency_ms`), and
            empty when no response was ever captured.
    """

    method: str
    endpoint: str
    query_params: Tuple[str, ...]
    body_shape: str
    response_shape: str
    triggered_by: Tuple[Tuple[str, str], ...]
    loaded_by: Tuple[str, ...] = ()
    status_codes: Tuple[int, ...] = ()
    latencies_ms: Tuple[int, ...] = ()
