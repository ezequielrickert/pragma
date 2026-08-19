# database/ladybug/state_styles.py

## module

`StateStyle` and `HAS_STATE_STYLE`: the declared `:hover` and `:focus` values a
control takes on.

**Observation tier, not a measurement, and that distinction is the whole
reason this exists.** `extract_pseudo_styles.js` reads `document.styleSheets`
and matches the declared rules against elements in their resting state. It never
hovers anything, needs no CDP session, and does not read geometry - so unlike
`rect`, these values do not depend on the viewport, on images loading, or on
anything being interacted with.

That is what lets them come from the ordinary discovery pass rather than from
the measurement pass they were originally written for, and it is why D10 got its
interaction states back without that pass being revived. The original code was
correct and simply lived in the wrong place; nothing about it had to change.

A new **table** rather than an altered one, which matters for existing
databases: `connect()` runs the DDL on every open, so `CREATE NODE TABLE IF NOT
EXISTS` picks up a new table on a `.lbdb` written by an older version.
Extending an existing table's `FROM`/`TO` list does not work that way - see
`docs/dev/generators/data_model.md`, where that difference is what scopes D14.

Its own module rather than part of `component.py`, which already sits at this
project's file-size watch threshold, and split-by-concern is the shape the rest
of this package uses.

## state_style_id

`<component id>|<state>|<property>`.

Keyed that way so a rediscovery **overwrites** one value rather than appending a
second: a control whose hover colour changed between runs reports the new value
with no stale row beside it. A `SERIAL` key would have made every re-crawl
double the table.

## _ladybugstatestylemixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)`.

## record_state_styles

Takes exactly what `extract_pseudo_styles.js` returns and `PageState.pseudo_styles`
carries - `[{"path", "states"}]`, with `states` being
`{"hover": {"color": "#fff"}, ...}`.

**Flattened to one row per (state, property)** rather than stored as the nested
shape. "Which hover colours does this site use" becomes a query instead of a
parse, which was the entire point of retiring the JSON blobs from this schema.

The `Component` is `MERGE`d, never `MATCH`ed, for the reason `containment.py`
documents at length: a `MATCH` that matches nothing drops the whole pattern
silently, so a control whose descriptive write has not landed yet would lose its
styles with no error at all.

Values that are empty strings are dropped before the write. A declaration with
no value is not a style.

## get_state_styles

Flat and unaggregated on purpose. `generators/design_tokens.py` counts these
into tokens, and that counting is the document's editorial decision - which
properties deserve a token, how ties break - not something this package should
have an opinion about. Same boundary `get_component_ledger` keeps for `options`.

**The page comes from `split_component_id`, not from a hop through
`HAS_COMPONENT`**, and that was a real bug before a test caught it. Reading
through the page undoes the write's `MERGE` entirely: a component with no
descriptive write has no `HAS_COMPONENT` edge, so its styles were stored and
then unreadable, which made the `MERGE`'s stated reason false.
`tests/test_ladybug_state_styles.py::test_a_style_for_a_component_not_yet_written_still_lands`
pins it.

Whole-site and zero-argument, so it is memoized in `CachingGraphStore` - both
the prose and JSON token documents call it.
