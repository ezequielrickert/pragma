"""JSON Lines serialization - one JSON object per line, sorted keys for a
deterministic diff. Shared by every per-run event-log document
(`evidence-log.jsonl`, `redaction-log.jsonl`) once a second one made the
identical two-line body worth naming once instead of twice.
Details: docs/dev/utils/jsonl.md#module
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


def as_jsonl(rows: List[Dict[str, Any]]) -> str:
    """Every row in `rows`, one compact JSON object per line.
    Details: docs/dev/utils/jsonl.md#as_jsonl
    """
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
