# database/ladybug/component.py

## module

`Component` and `Interaction` - the observation tier's record of what is on a
page and what was done to it.

Relies on `self._ensure_page(...)` from `page.py`'s mixin through the MRO, so a
component can be written for a page the crawl has not formally arrived at yet.

**The interaction is a node, not a set of columns on an edge.** That is the
change the storage migration turned on, and the one that unblocked
`generators/user_flows.py`: an `Interaction` carries `visit_id` and `step_seq`,
so a control clicked twice keeps each click's requests and outcome separate
instead of pooling them onto the component and losing which belonged to which.

## _ladybugcomponentmixin

Mixed into `LadybugGraphStore`, relies on `self._call(...)` and
`self._ensure_page(...)`.

## _component_params

The descriptive parameter set one component write needs, with `ComponentFacts`
flattened in. Shared by `record_component` and `record_components` so the
single and batched paths cannot disagree about what a component write consists
of - `item` is either the kwargs of the first or one entry of the second's
batch, both already dict-shaped.

## record_component

Creates or refreshes a component's **descriptive** fields only.
`interacted` and `interaction_count` are untouched by a rediscovery, and are
bootstrapped solely by the schema's own `DEFAULT` on first creation.

That split is what makes rediscovery safe. A page visited a second time
re-reports every component it finds, and if that write reset the ledger the
crawl would forget what it had already interacted with and loop.
`DESCRIPTIVE_COMPONENT_FIELDS` in `schema.py` is the list both this and the
`ON MATCH` clause derive from, so the two cannot drift.

## record_components

One `UNWIND` for a whole discovery pass. A component-heavy real page produces
100-300+ components, and one round-trip each through the single writer thread
was the measured cost this replaced.

## record_component_interaction

Marks the component interacted with and appends one `Interaction`, `PERFORMED`
from its `Component` and `RESULTED_IN` the page it left you on.

**An interaction that did not navigate points back at its own page**, never at
nothing. A dangling reference would make "stayed here" indistinguishable from
"we lost track", and every read that walks `RESULTED_IN` would need a special
case.

`resulting_url` is `route_shape`d here, unlike every other page key in this
package, which callers shape before calling. `PageVisitor.visit` is the one
caller that passes a `clean_url`'d literal on purpose, so the shaping happens
at this boundary rather than being required of it.

## get_component_states

Every known component for one page, one query per page visit. Read by
`GraphStoreInteractionTracker` to decide what has already been touched - which
is what makes "already interacted" survive across a multi-run crawl rather
than only within one process.

## count_unexplored_components

`(unexplored, total)` across the site. Feeds the coverage banner's second
number, so its `semantic_only` default matters: the `cursor: pointer`
catch-all layer would otherwise inflate the denominator with elements no
reader thinks of as components.

## get_component_ledger

The whole-site per-component record: `{page_url: {path: record}}`, each record
carrying its ordered `interactions`, the `network_requests` those triggered,
and its `options` as `(rows, group_name)`.

**`options` is raw `Option` data, not the normalized `{"kind", ...}` shape.**
The reconstruction lives in `generators/component_classifier.py`
(`describe_options_from_rows`) because this package must not depend on
`generators/` - the same layering `ComponentFamily`'s docstring states. A
caller that wants the normalized shape calls that function itself.

That boundary is also where a real regression hid: `component_catalog.py` kept
reading a flat `option_labels` key that the `Option` table replaced, and every
dropdown in D5 silently lost its options. See
`docs/dev/generators/component_catalog.md#_with_option_labels`.

This is the heaviest read in the project and had ~8 callers per run, which is
what `CachingGraphStore` exists for.
