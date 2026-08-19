# database/ladybug/raw_query.py

## module

The guarded raw-Cypher escape hatch, and the schema summary that exists
alongside it.

**Who this is for.** `research/rag-over-neo4j-for-future-qa.md` concluded that
a local model must never drive a raw tool call, and this project's own
`wiki/local-and-small-model-constraints.md` documents why. So `raw()` is for a
capable model or a human operator; the crawl's own local-model narration passes
stay on `named_queries.py`'s bounded library.

**What the guard is and is not.** It is a keyword-and-shape guard that rejects
anything that looks like a write. It is **not** a parser, and not a sandbox. It
raises the cost of an accidental write to something a reviewer will notice; it
does not make the method safe to expose to untrusted input.

## _reject_reason

`None` when a query passes, otherwise the reason - so the caller gets a
message naming what tripped, rather than a bare refusal.

Three separate guards, because one regex could not cover all three:

- **Forbidden keywords**, whole-word and case-insensitive: `CREATE`, `MERGE`,
  `DELETE`, `SET`, `DROP`, transaction control, and the rest. Matched with
  `\b` so a property named `created_at` does not false-positive - an
  underscore is a word character, so `\b` does not split `CREATE` from
  `_FTS_INDEX` either, which is what makes the next guard necessary.
- **Mutating procedure calls**, matched by procedure-name prefix
  (`CALL CREATE_`, `CALL DROP_`, `CALL DELETE_`). `CREATE_FTS_INDEX` is a
  write that the keyword guard above provably cannot see, for exactly the
  `\b` reason just described.
- **Read openers**: a query has to start with `MATCH`, `OPTIONAL MATCH`,
  `WITH`, `UNWIND`, `CALL` or `RETURN`. Anything else - a bare procedure
  invocation, a leading semicolon, empty input - is rejected rather than
  guessed at.

## raw

Runs a read-only Cypher string and returns rows.

**The result cap is applied in Python, after execution, not injected into the
query.** There is no way to append a `LIMIT` to an arbitrary string that stays
correct when the string already has its own `LIMIT` or an `ORDER BY`, so
truncating the materialized list is the one approach that is right regardless
of the query's shape. The consequence is honest and worth knowing: the engine
still does the full work, the cap only bounds what comes back.

## schema_card

The schema as text, for a caller - human or model - that needs to know what
tables exist before writing a query. Derived from `DDL` rather than
maintained separately, so it cannot describe a table that was renamed.

## _ladybugrawquerymixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`, same contract as
every other mixin here.
