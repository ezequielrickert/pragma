# database/ladybug/_cypher.py

## module

`SET`-clause building, shared by every mixin whose batched (`UNWIND`) writes
touch a numeric column that can be uniformly `None` across one batch.

**The bug this exists to prevent.** Ladybug infers an `UNWIND` row column's type
from the values in the batch. When a numeric column is `None` on *every* row, it
infers `STRING` and rejects the write against a `DOUBLE`/`INT64` column.
Confirmed against the real engine.

Both all-`None` batches are ordinary, not pathological:

- Component geometry, when discovery could not measure any element in the pass.
- `Page.click_depth`, when no page is reachable from the root - a disconnected
  crawl.

The fix is an explicit `CAST` on every numeric column. It belongs in one place
that all the mixins import rather than repeated inline per mixin, because the
failure only appears for a whole-batch-`None` case that a hand-written clause in
a new module will not obviously be missing.

`analysis.py` writes its own clause instead of importing this, and says so in a
comment: its `SET` is short enough that pulling in the helper would obscure more
than it shares. That is a deliberate exception, and the reason it is written
down there is so the next reader does not "fix" the inconsistency by accident.

## set_clause

Builds `"c.tag = $tag, c.x = CAST($x AS DOUBLE), ..."` - or `r.`-prefixed for an
`UNWIND` row - from a field list. Every descriptive `SET` in this package,
single-item and batched alike, derives from this call, so the cast rule is
applied in exactly one place and a new field gets it by existing.
