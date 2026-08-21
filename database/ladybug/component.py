"""Component/Interaction write path for `LadybugGraphStore` - split from
`page.py`/`text_content.py` for the same file-size reason the retired
DuckDB backend split `_duckdb_component_store.py` out on its own.
`_LadybugComponentMixin` is combined into the public `LadybugGraphStore`
class via multiple inheritance and relies on `self._call(...)`/
`self._ensure_page(...)` (defined on `page.py`'s mixin, resolved through
`LadybugGraphStore`'s MRO) existing on whatever it ends up mixed into.

Storage-migration plan step 4, then the canonical-schema migration
(issue #134): `Component.id` is content-derived and page-decoupled
(`ids.py::component_content_id`), so a discovery no longer creates a node
per page - it `MERGE`s onto whichever row already has identical content,
anywhere in the site. `path`/`element_id`/geometry moved off the node
entirely, onto `HAS_COMPONENT` as page-instance data.

Details: docs/dev/database/ladybug/component.md#module
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from core.interfaces import ComponentFacts, VisitStep
from utils.urls import route_shape
from ._component_lookup import resolve_component_ids, stub_component_id
from ._cypher import set_clause
from .ids import component_content_id
from .schema import DESCRIPTIVE_COMPONENT_FIELDS

_SET_CLAUSE = set_clause("c", DESCRIPTIVE_COMPONENT_FIELDS)
_SET_CLAUSE_UNWIND = set_clause("c", DESCRIPTIVE_COMPONENT_FIELDS, row_alias="r.")
# `path` is a MERGE key on HAS_COMPONENT itself (below), not a plain SET -
# two distinct DOM instances on the *same* page whose content happens to
# be identical (two identical icon buttons, two identical card templates)
# still need two separate edges to the one canonical Component they share,
# and MERGE only gets that by including path in the pattern it matches on.
_EDGE_FIELDS = ("element_id", "x", "y", "width", "height")
_EDGE_SET_CLAUSE = set_clause("e", _EDGE_FIELDS)
_EDGE_SET_CLAUSE_UNWIND = set_clause("e", _EDGE_FIELDS, row_alias="r.")


def _node_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    """The descriptive fields that stay on `Component` - everything
    `DESCRIPTIVE_COMPONENT_FIELDS` names, `item` being either the kwargs
    `record_component` was called with or one entry of `record_components`'
    batch list, both already dict-shaped.
    Details: docs/dev/database/ladybug/component.md#_node_fields
    """
    facts = item.get("facts") or ComponentFacts()
    fields = {
        "tag": item.get("tag", ""), "text": item.get("text", ""),
        "role": item.get("role", ""), "input_type": item.get("input_type", ""),
        "visible": item.get("visible", True), "layer": item.get("layer", "semantic"),
        "component_type": item.get("component_type", ""),
        **asdict(facts),
    }
    fields.pop("element_id", None)
    return fields


def _component_params(path: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """One component write's full param set: its node fields (`id` filled
    in by the caller once it knows whether this path was already known -
    see `record_component`/`record_components`) and the page-instance
    fields `HAS_COMPONENT` carries instead of the node (`path`,
    `element_id`, geometry).
    Details: docs/dev/database/ladybug/component.md#_component_params
    """
    facts = item.get("facts") or ComponentFacts()
    node_fields = _node_fields(item)
    return {
        "path": path, "element_id": facts.element_id,
        "x": item.get("x"), "y": item.get("y"), "width": item.get("width"), "height": item.get("height"),
        **node_fields,
    }


class _LadybugComponentMixin:
    """Details: docs/dev/database/ladybug/component.md#_ladybugcomponentmixin"""

    def record_component(
        self,
        page_url: str,
        path: str,
        tag: str = "",
        text: str = "",
        role: str = "",
        input_type: str = "",
        visible: bool = True,
        layer: str = "semantic",
        x: Optional[float] = None,
        y: Optional[float] = None,
        width: Optional[float] = None,
        height: Optional[float] = None,
        component_type: str = "",
        facts: Optional[ComponentFacts] = None,
    ) -> None:
        """Create or refresh a Component node's descriptive fields, and
        the `HAS_COMPONENT` edge carrying this page's rendering of it -
        `interacted`/`interaction_count` are untouched by a rediscovery,
        bootstrapped only by the schema's own `DEFAULT` on first creation.

        This exact `(page_url, path)` slot's existing `HAS_COMPONENT` edge,
        if any, decides `id` ahead of content-hashing a fresh one - a
        rediscovery whose content drifted slightly (a client-side text
        update, a class toggle) still updates the *same* row rather than
        minting a new canonical id and orphaning the old one's `interacted`/
        `interaction_count` ledger. Content-hash collapse
        (`ids.py::component_content_id`) only decides identity the first
        time this slot is ever seen.
        Details: docs/dev/database/ladybug/component.md#record_component
        """
        item = {
            "tag": tag, "text": text, "role": role, "input_type": input_type,
            "visible": visible, "layer": layer, "x": x, "y": y, "width": width, "height": height,
            "component_type": component_type, "facts": facts,
        }
        params = _component_params(path, item)

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            resolved = resolve_component_ids(conn, page_url, [path])
            target_id = resolved.get(path) or component_content_id(_node_fields(item))
            conn.execute(
                f"""
                MERGE (c:Component {{id: $id}})
                SET {_SET_CLAUSE}
                WITH c
                MATCH (p:Page {{url: $page_url}})
                MERGE (p)-[e:HAS_COMPONENT {{path: $path}}]->(c)
                SET {_EDGE_SET_CLAUSE}
                """,
                {**params, "id": target_id, "page_url": page_url},
            )

        self._call(op)

    def record_components(self, page_url: str, components: List[Dict[str, Any]]) -> None:
        """Batched `record_component`: one `UNWIND` for a whole discovery
        pass's components instead of one round-trip each - collapses the
        100-300+ individual writes a component-heavy real page produces,
        same motivation as the retired DuckDB backend's `executemany`
        version.
        Details: docs/dev/database/ladybug/component.md#record_components
        """
        if not components:
            return

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            # Same rediscovery-continuity rule as record_component: a path
            # already known on this page keeps its existing id even if its
            # content drifted; only a path seen here for the first time
            # gets a fresh content hash, which is what lets it collapse
            # onto a matching row from another page.
            resolved = resolve_component_ids(conn, page_url, (item["path"] for item in components))
            rows = []
            for item in components:
                params = _component_params(item["path"], item)
                target_id = resolved.get(item["path"]) or component_content_id(_node_fields(item))
                rows.append({**params, "id": target_id})
            # Page matched before UNWIND, not after via WITH - a MATCH
            # following a WITH that itself follows an UNWIND raised "Cannot
            # evaluate expression with type VARIABLE" against the real
            # engine (confirmed live; the single-item, non-UNWIND version
            # of this same WITH shape works fine).
            conn.execute(
                f"""
                MATCH (p:Page {{url: $page_url}})
                UNWIND $rows AS r
                MERGE (c:Component {{id: r.id}})
                SET {_SET_CLAUSE_UNWIND}
                MERGE (p)-[e:HAS_COMPONENT {{path: r.path}}]->(c)
                SET {_EDGE_SET_CLAUSE_UNWIND}
                """,
                {"rows": rows, "page_url": page_url},
            )

        self._call(op)

    def record_component_interaction(
        self,
        page_url: str,
        path: str,
        action: str,
        value: str = "",
        resulting_url: str = "",
        source_path: str = "",
        step: Optional[VisitStep] = None,
        blocked: bool = False,
        blocked_reason: str = "",
    ) -> None:
        """Mark a component as interacted with and append one interaction
        record - an `Interaction` node, `PERFORMED` from its `Component`,
        `RESULTED_IN` the page it left you on, and `OCCURRED_ON` the page
        it happened on (the last one explicit now that `Component` is
        canonical and no longer implies it the way an embedded `page_url`
        once did). An interaction that didn't navigate points `RESULTED_IN`
        back at its own page, never a dangling reference - same rule the
        retired DuckDB backend's `target_url = resulting_url or page_url`
        followed.

        `resulting_url` is `route_shape`d before it names a page here,
        even though every other caller in this codebase already shapes
        its own page keys before calling anything in this package -
        `PageVisitor.visit` is the one exception, passing `clean_url`'d
        (literal) values into this specific parameter on purpose
        (`ComponentInteraction.resulting_url` tracks literal identity for
        its own physical-navigation-detection reasons). Left unshaped, a
        route whose literal address changes every visit (a session-token
        page revisiting itself) reads as "navigated to a brand new page"
        indefinitely - confirmed live: a `Page` node with the same shape
        as an already-canonical one, keyed by its own un-shaped literal
        self. Every other page identity that reaches storage is already
        canonical; this is the one write path that has to enforce it
        itself rather than trust the caller.

        `blocked`/`blocked_reason` record the mode-gate handler
        (`spiders/browser/crawl4ai_crawler/hooks.py`) having intercepted
        at least one mutating request this interaction tried to fire, in
        `immutable` mode - decided by issue #59's schema research. A
        blocked mutation never reaches the network, so it has no
        `Request`/`TRIGGERED` pair of its own; these two scalars on the
        `Interaction` itself are the only trace of it.

        The component this interaction is against is resolved through
        the page's `HAS_COMPONENT` edges by `path` - real crawls always
        discover a component before interacting with it, so this is
        expected to find it. The blank-content fallback
        (`_component_lookup.stub_component_id`) only guards against
        interacting with a component discovery itself somehow missed.
        Details: docs/dev/database/ladybug/component.md#record_component_interaction
        """
        target_url = route_shape(resulting_url) if resulting_url else page_url
        params = {
            "page_url": page_url, "path": path, "target_url": target_url,
            "action": action, "value": value, "source_path": source_path,
            "visit_id": step.visit_id if step else "", "step_seq": step.seq if step else 0,
            "blocked": blocked, "blocked_reason": blocked_reason,
        }

        def op(conn) -> None:
            self._ensure_page(conn, page_url)
            self._ensure_page(conn, target_url)
            resolved = resolve_component_ids(conn, page_url, [path])
            component_id = resolved.get(path) or stub_component_id(page_url, path)
            # One statement, not a MERGE-then-CREATE pair - a component
            # discovered mid-crawl is expected to already exist here (the
            # fallback path only guards against the rare discovery miss
            # documented above), and there is no reason to split an
            # otherwise-atomic write into two round trips.
            #
            # MERGE (page)-[e:HAS_COMPONENT]->(c), not just MERGE (c): a
            # component's own Page edge is what get_component_ledger joins
            # through, and record_component/record_components is what
            # normally creates it. Real crawls always discover a component
            # before interacting with it, so this only matters for the
            # fallback case - but the same completeness guarantee
            # `_ensure_component_stub` gave the retired DuckDB backend
            # (any write path produces a queryable component) has to hold
            # here too, confirmed the hard way: without this, a component
            # that only ever appears via this method is invisible to
            # get_component_ledger's page-to-component join entirely.
            conn.execute(
                """
                MATCH (page:Page {url: $page_url})
                MERGE (c:Component {id: $component_id})
                MERGE (page)-[e:HAS_COMPONENT {path: $path}]->(c)
                WITH c, page
                MATCH (target:Page {url: $target_url})
                CREATE (i:Interaction {
                    action: $action, value: $value, source_path: $source_path,
                    visit_id: $visit_id, step_seq: $step_seq,
                    blocked: $blocked, blocked_reason: $blocked_reason
                })
                CREATE (c)-[:PERFORMED]->(i)
                CREATE (i)-[:RESULTED_IN]->(target)
                CREATE (i)-[:OCCURRED_ON]->(page)
                SET c.interacted = true, c.interaction_count = c.interaction_count + 1
                """,
                {**params, "component_id": component_id},
            )

        self._call(op)

    def get_component_states(self, page_url: str) -> Dict[str, Dict[str, Any]]:
        """All known components for one page, one query per page visit -
        read by `GraphStoreInteractionTracker` to decide what's already
        been interacted with.
        Details: docs/dev/database/ladybug/component.md#get_component_states
        """
        fields = ", ".join(f"c.{field}" for field in DESCRIPTIVE_COMPONENT_FIELDS)

        def op(conn) -> Dict[str, Dict[str, Any]]:
            rows = conn.execute(
                f"""
                MATCH (:Page {{url: $page_url}})-[e:HAS_COMPONENT]->(c:Component)
                RETURN e.path, c.interacted, c.interaction_count, {fields}
                """,
                {"page_url": page_url},
            )
            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                path, interacted, interaction_count = row[0], row[1], row[2]
                result[path] = {"interacted": interacted, "interaction_count": interaction_count}
                result[path].update(zip(DESCRIPTIVE_COMPONENT_FIELDS, row[3:]))
            return result

        return self._call(op)

    def count_unexplored_components(self, semantic_only: bool = True) -> Tuple[int, int]:
        """`(unexplored_count, total_count)` of components tracked across
        the whole site.
        Details: docs/dev/database/ladybug/component.md#count_unexplored_components
        """
        clause = "WHERE c.layer <> 'pointer'" if semantic_only else ""

        def op(conn) -> Tuple[int, int]:
            row = list(conn.execute(
                f"MATCH (c:Component) {clause} "
                "RETURN sum(CASE WHEN c.interacted THEN 0 ELSE 1 END), count(*)"
            ))[0]
            # int(), not the bare Decimal sum() returns - see page.py's
            # count_visited for why this matters.
            return (int(row[0] or 0), row[1])

        return self._call(op)

    def count_interactions(self) -> int:
        """How many interaction events the crawl actually performed - the
        `triggered` half of `generators/coverage.py`'s `interactions`
        counters (docs/adr/0001); `count_unexplored_components`'s total is
        the `detected` half (how many interaction-capable components
        exist, whether or not each was ever exercised).
        Details: docs/dev/database/ladybug/component.md#count_interactions
        """
        def op(conn) -> int:
            row = list(conn.execute("MATCH (i:Interaction) RETURN count(*)"))[0]
            return int(row[0])

        return self._call(op)

    def get_interaction_evidence(self) -> List[Dict[str, Any]]:
        """Every `Interaction` node, its own auto-increment `id`
        (`interaction:<id>`, ADR-0017) plus enough context for a one-line
        summary - the page/component it happened on, the action, the
        value. `evidence-log.jsonl` is what makes this citation resolvable
        to anyone reading `derived_from` from outside the graph.

        Resolved through `OCCURRED_ON`, not a bare `HAS_COMPONENT` hop
        from `Component`: a canonical component can carry many
        `HAS_COMPONENT` edges (one per page rendering it), so only
        `OCCURRED_ON` names the one page this specific interaction
        actually happened on.
        Details: docs/dev/database/ladybug/component.md#get_interaction_evidence
        """
        def op(conn) -> List[Dict[str, Any]]:
            rows = conn.execute(
                """
                MATCH (c:Component)-[:PERFORMED]->(i:Interaction)-[:OCCURRED_ON]->(p:Page)
                MATCH (p)-[e:HAS_COMPONENT]->(c)
                RETURN i.id, p.url, e.path, i.action, i.value
                ORDER BY i.id
                """
            )
            return [
                {"id": row[0], "page_url": row[1], "path": row[2], "action": row[3], "value": row[4]}
                for row in rows
            ]

        return self._call(op)

    def get_component_ledger(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """Full per-component record for the whole site, `{page_url:
        {path: record}}`, each record carrying its own ordered
        `interactions` list, the `network_requests` its interactions
        triggered, and its `options` as `(rows, group_name)` - raw
        `Option` data, not the normalized `{"kind", ...}` shape
        `generators/component_classifier.py::describe_options_from_rows`
        builds from it. That reconstruction stays in `generators/`
        deliberately: this package must not depend on it (`ComponentFamily`'s
        own docstring states the layering this mirrors), so a caller that
        wants the normalized shape calls
        `describe_options_from_rows(*record["options"])` itself.

        Base component rows come from `HAS_COMPONENT`, one entry per
        (page, path) rendering - a canonical component shared by several
        pages produces one ledger entry per page, each carrying the same
        descriptive fields, exactly the "known once, applies everywhere"
        shape collapse is for. Interaction/request/option rows are
        attributed through `OCCURRED_ON` (interactions) or the same
        `HAS_COMPONENT` `path`, never through a bare hop off the now-
        canonical `Component`, which would otherwise fan an interaction
        out across every page that happens to share the component.
        Details: docs/dev/database/ladybug/component.md#get_component_ledger
        """
        fields = ", ".join(f"c.{field}" for field in DESCRIPTIVE_COMPONENT_FIELDS)
        edge_fields = ", ".join(f"e.{field}" for field in _EDGE_FIELDS)

        def op(conn) -> Dict[str, Dict[str, Dict[str, Any]]]:
            component_rows = conn.execute(
                f"""
                MATCH (p:Page)-[e:HAS_COMPONENT]->(c:Component)
                RETURN p.url, e.path, c.interacted, c.interaction_count, {fields}, {edge_fields}
                """
            )
            ledger: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for row in component_rows:
                page_url, path, interacted, interaction_count = row[0], row[1], row[2], row[3]
                node_field_count = len(DESCRIPTIVE_COMPONENT_FIELDS)
                record: Dict[str, Any] = {"interacted": interacted, "interaction_count": interaction_count}
                record.update(zip(DESCRIPTIVE_COMPONENT_FIELDS, row[4:4 + node_field_count]))
                # This page's own rendering of the (possibly shared) canonical
                # component - path/element_id/geometry, moved off Component
                # onto HAS_COMPONENT by #134, belong exactly here: the ledger
                # is already keyed per page, the level these facts are true at.
                record.update(zip(_EDGE_FIELDS, row[4 + node_field_count:]))
                record["interactions"] = []
                record["network_requests"] = []
                record["options"] = ([], "")
                ledger.setdefault(page_url, {})[path] = record

            interaction_rows = conn.execute(
                """
                MATCH (c:Component)-[:PERFORMED]->(i:Interaction)-[:OCCURRED_ON]->(p:Page)
                MATCH (p)-[e:HAS_COMPONENT]->(c)
                MATCH (i)-[:RESULTED_IN]->(target:Page)
                RETURN p.url, e.path, i.action, i.value, target.url, i.source_path, i.visit_id, i.step_seq
                ORDER BY i.id
                """
            )
            for page_url, path, action, value, target_url, source_path, visit_id, step_seq in interaction_rows:
                page_components = ledger.get(page_url)
                if page_components is None or path not in page_components:
                    continue
                page_components[path]["interactions"].append(
                    {
                        "action": action, "value": value,
                        # "" when target_url == page_url, not the literal
                        # target - RESULTED_IN always points somewhere
                        # (record_component_interaction defaults a non-
                        # navigating interaction's target to its own page),
                        # so the empty-string-means-no-navigation contract
                        # every reader depends on (TraceStep.navigated,
                        # component_tree.py's redirect_target fallback) has
                        # to be reconstructed here, not read off verbatim.
                        "resulting_url": target_url if target_url != page_url else "",
                        "source_path": source_path, "visit_id": visit_id, "step_seq": step_seq,
                    }
                )

            request_rows = conn.execute(
                """
                MATCH (c:Component)-[:PERFORMED]->(i:Interaction)-[:OCCURRED_ON]->(p:Page)
                MATCH (p)-[e:HAS_COMPONENT]->(c)
                MATCH (i)-[:TRIGGERED]->(req:Request)
                RETURN p.url, e.path, req.method, req.path, req.status, req.failed, req.failure_text,
                       i.visit_id, i.step_seq
                ORDER BY req.id
                """
            )
            for page_url, path, method, req_path, status, failed, failure_text, visit_id, step_seq in request_rows:
                page_components = ledger.get(page_url)
                if page_components is None or path not in page_components:
                    continue
                page_components[path]["network_requests"].append(
                    {
                        "method": method, "path": req_path, "status": status,
                        "failed": failed, "failure_text": failure_text,
                        "visit_id": visit_id, "step_seq": step_seq,
                    }
                )

            option_rows = conn.execute(
                """
                MATCH (p:Page)-[e:HAS_COMPONENT]->(c:Component)-[hop:HAS_OPTION]->(o:Option)
                RETURN p.url, e.path, o.group_name, o.path, o.text, o.selected, hop.seq
                ORDER BY hop.seq
                """
            )
            for page_url, path, group_name, opt_path, opt_text, opt_selected, _seq in option_rows:
                page_components = ledger.get(page_url)
                if page_components is None or path not in page_components:
                    continue
                rows, _ = page_components[path]["options"]
                rows.append({"path": opt_path, "text": opt_text, "selected": opt_selected})
                page_components[path]["options"] = (rows, group_name)
            return ledger

        return self._call(op)
