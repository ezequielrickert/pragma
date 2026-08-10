"""Structured JSON export of a crawled site's graph, for downstream tooling.
Details: docs/dev/generators/graph_export.md#module
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from ..core.interfaces import GraphStore


def build_graph_export(graph_store: GraphStore, site: str) -> Dict[str, Any]:
    """Pure, deterministic read of every relevant `GraphStore` query into one dict.
    Details: docs/dev/generators/graph_export.md#build_graph_export
    """
    rows = graph_store.get_progress_table_rows(site)
    titles = graph_store.get_page_titles(site)
    descriptions = graph_store.get_page_descriptions(site)
    edges = graph_store.get_edges(site)
    component_ledger = graph_store.get_component_ledger(site)
    text_content_ledger = graph_store.get_text_content_ledger(site)

    pages = []
    for row in rows:
        url = row["url"]
        pages.append(
            {
                "url": url,
                "status": row.get("status"),
                "components": row.get("components"),
                "label": row.get("label"),
                "title": titles.get(url, ""),
                "description": descriptions.get(url, ""),
            }
        )

    return {
        "site": site,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "edges": edges,
        "component_ledger": component_ledger,
        "text_content_ledger": text_content_ledger,
    }


def generate_graph_export_document(graph_store: GraphStore, site: str) -> str:
    """Top-level entry point `Engine` calls: build_graph_export, pretty JSON.
    Details: docs/dev/generators/graph_export.md#generate_graph_export_document
    """
    return json.dumps(build_graph_export(graph_store, site), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
