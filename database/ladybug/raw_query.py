"""The guarded raw-Cypher escape hatch and the schema summary it exists
alongside - storage-migration plan step 9. `_LadybugRawQueryMixin` is
combined into the public `LadybugGraphStore` class via multiple
inheritance and relies on `self._call(...)` existing on whatever it ends
up mixed into.

Per `research/rag-over-neo4j-for-future-qa.md` - a local model must never
drive a raw tool call - `raw()` exists for a capable model or a human
operator, not the crawl's own local-model narration passes, which stay on
`database/ladybug/named_queries.py`'s query library.

Details: docs/dev/database/ladybug/raw_query.md#module
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .schema import DDL

# The result cap `raw()` truncates to when a query's own RETURN carries no
# LIMIT - applied in Python after execution, not injected into the query
# text: Cypher has no syntax for "add a LIMIT to whatever this string
# already is" that survives a query that already has its own LIMIT/ORDER
# BY, so truncating the materialized result list is the one approach that
# is correct regardless of what shape the caller's query takes.
_DEFAULT_RAW_LIMIT = 1000

# Whole-word, case-insensitive: any of these appearing in a raw query
# marks it a write/DDL statement, not a read - rejected outright. Matched
# with \b so a property or column named e.g. "created_at" or a procedure
# name like CREATE_FTS_INDEX (an underscore is a word character, so \b
# does not split CREATE from _FTS) does not false-positive.
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|DROP|ALTER|INSTALL|LOAD|COPY|EXPORT|"
    r"IMPORT|ATTACH|RENAME|BEGIN|COMMIT|ROLLBACK|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# A CALL to a mutating procedure (CREATE_FTS_INDEX, DROP_FTS_INDEX, ...)
# is a write even though "CALL" itself is a read-shaped keyword and
# "CREATE_FTS_INDEX" never matches _FORBIDDEN_KEYWORDS above (no word
# boundary before "_FTS_INDEX") - caught separately by procedure-name
# prefix instead of by keyword.
_MUTATING_CALL = re.compile(r"\bCALL\s+(CREATE|DROP|DELETE)_", re.IGNORECASE)

# What a read is allowed to open with. A raw query that starts anywhere
# else (a bare procedure invocation with no leading CALL, a semicolon,
# empty input) is rejected rather than guessed at.
_READ_OPENERS = re.compile(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH|UNWIND|CALL|RETURN)\b", re.IGNORECASE)


def _reject_reason(cypher: str) -> Optional[str]:
    """`None` if `cypher` passes every guard below, else why it was
    rejected. A guard, not a parser or a full sandbox - see this
    module's own docstring and `raw()`'s for what that does and does not
    promise.
    Details: docs/dev/database/ladybug/raw_query.md#_reject_reason
    """
    stripped = cypher.strip()
    if not stripped:
        return "empty query"
    statements = [s for s in stripped.split(";") if s.strip()]
    if len(statements) > 1:
        return "multiple statements in one raw() call"
    if not _READ_OPENERS.match(stripped):
        return "must open with MATCH/OPTIONAL MATCH/WITH/UNWIND/CALL/RETURN"
    if _MUTATING_CALL.search(stripped):
        return "CALL to a mutating procedure is not a read"
    forbidden = _FORBIDDEN_KEYWORDS.search(stripped)
    if forbidden:
        return f"write/DDL keyword not allowed in raw(): {forbidden.group(1)}"
    return None


class _LadybugRawQueryMixin:
    """Details: docs/dev/database/ladybug/raw_query.md#_ladybugrawquerymixin"""

    def schema_card(self) -> str:
        """The full DDL, verbatim - already comment-free Cypher (Ladybug
        rejects `--` inline comments anywhere inside a string passed to
        `execute()`, confirmed against the real engine while building the
        schema itself) with every table and column named for what it
        means, and no `site` predicate anywhere to explain away. This is
        the actual "readable by AI" property the storage-migration plan
        set out for - more than the query language sitting on top of it.
        Details: docs/dev/database/ladybug/raw_query.md#schema_card
        """
        return DDL.strip()

    def raw(
        self, cypher: str, params: Optional[Dict[str, Any]] = None,
        *, limit: int = _DEFAULT_RAW_LIMIT, timeout_s: int = 30,
    ) -> List[List[Any]]:
        """Read-only Cypher escape hatch for a capable model or a human
        operator - never the crawl's own passes, which use
        `named_queries.py`'s methods.

        Rejects (raises `ValueError`, query never reaches the engine):
        multiple statements, anything not opening on a read-shaped
        clause, any write/DDL keyword, and a `CALL` to a mutating
        procedure. This is a guard against an accidental or careless
        write, not a full SQL-injection-grade sandbox - a sufficiently
        determined adversarial query could still find a gap a real parser
        would close; the honest claim is "rejects the write shapes a
        model asking a genuine question would produce," not "provably
        safe against anything."

        Args:
            cypher: a single `MATCH`/`OPTIONAL MATCH`/`WITH`/`UNWIND`/
                `CALL`/`RETURN`-opening statement.
            params: bound parameters, same as every other method in this
                package - never string-interpolate a caller-supplied
                value into `cypher` itself.
            limit: max rows returned - applied to the materialized result
                after execution (Cypher has no portable way to inject a
                LIMIT into an arbitrary query string that might already
                carry its own), so a query already narrower than this
                never notices it.
            timeout_s: query timeout, applied to the shared writer
                connection for the duration of this one call only - reset
                immediately after, since every other write/read on this
                store shares that same connection.

        Returns:
            One list per result row, in whatever column order the query's
            own `RETURN` specified.
        Details: docs/dev/database/ladybug/raw_query.md#raw
        """
        reason = _reject_reason(cypher)
        if reason is not None:
            raise ValueError(f"raw() rejected the query: {reason}")

        def op(conn) -> List[List[Any]]:
            conn.set_query_timeout(timeout_s * 1000)
            try:
                rows = list(conn.execute(cypher, params or {}))
            finally:
                conn.set_query_timeout(0)
            return rows[:limit]

        return self._call(op)
