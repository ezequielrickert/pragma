# database/ladybug/_query_rows.py

## module

Narrows `Connection.execute(...)`'s result to the shape every read path in
this package actually gets back, added when the codebase adopted mypy
strict mode (issue #250).

`lb.Connection.execute` is typed `QueryResult | list[QueryResult]` -
Ladybug returns a `list[QueryResult]` only for a multi-statement query
string (several `;`-separated statements in one call), and every call site
in this package passes exactly one statement. Each row within a single
`QueryResult` is typed `list[Any] | dict[str, Any]` - the `dict` half only
appears once `QueryResult.rows_as_dict()` has been called (confirmed
against `ladybug/query_result.py`), which nothing in this package ever
does, so every row actually reaching a caller here is a plain positional
`list[Any]`.

## rows

Asserts both narrowings instead of re-deriving them at each of the ~30
call sites that iterate a query result by position (`row[0]`,
tuple-unpacking) - one place to assert the shape that's actually true,
rather than a `# type: ignore` at every call site or a runtime check
duplicated ~30 times. Raises `AssertionError` with a pointer to the likely
cause if either narrowing is ever wrong, instead of silently misreading a
`dict`-shaped row as a list.
