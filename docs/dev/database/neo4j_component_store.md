# `database/neo4j_component_store.py`

## module

Component CRUD for `Neo4jGraphStore`, split out to keep that file under
this project's file-size threshold. `_Neo4jComponentMixin` is mixed into
the public class rather than being instantiated on its own, so every method
here assumes `self._session()` exists on whatever it lands in.

## _Neo4jComponentMixin

Holds the Component half of the store: discovery writes
(`record_component`/`record_components`), the interaction and options and
network ledgers, and the two read paths (`get_component_states` for one
page during a crawl, `get_component_ledger` for the whole site afterward).

## interacted

Interactions used to be a `c.interactions` array of JSON **strings**. In
Neo4j Browser that renders as `["{\"action\": \"click\", ...}"]` - the most
valuable data in the graph, in its least readable possible form, and
unreachable from Cypher without string matching.

They are now `:INTERACTED` relationships. Every interaction points at a
`:Page`:

- one that navigated points at where it **landed**, so
  `(:Component)-[:INTERACTED]->(:Page)` is a real traversal of "what does
  this control do";
- one that didn't points back at its **own** page. The alternative -
  leaving non-navigating interactions unconnected - would need either a
  separate node kind or a dangling edge, and would break the single query
  above into two. `navigated` distinguishes the two cases, so nothing is
  lost by giving them the same shape.

`seq` comes from `c.interaction_count`, incremented in the same query that
creates the edge. It replaces what the old array got for free from append
order: without it, reading interactions back is unordered, and a stepper's
`+ + -` would be indistinguishable from `- + +`. A timestamp alone was not
enough - two interactions can share one.

`get_component_ledger` reassembles the same dicts the array held, so no
reader changed. The one visible difference is that `source_path` is now
always present (blank included), because a relationship property exists on
every edge; every reader already treated `""` as absent.

**This is a breaking change to stored data.** A graph written by the
previous version has interactions in the old array and none in the new
relationships, and reads back as if nothing was ever interacted with.
`PragmaConfig.fresh` defaults to `true` and purges the site before every
crawl, so a normal run is unaffected; a `fresh: false` graph needs a
re-crawl.

## caption

Short display property for Neo4j Browser: the component's visible text
(truncated to 40 chars), else its `component_type`, else its `tag`.

Named `caption`, not `name`, and that is not cosmetic: `ComponentFacts.name`
is the DOM `name` attribute and is already persisted as `c.name`. A first
attempt used `name` for both, and since `_FACTS_FIELDS` is appended *after*
the caption clause in `_COMPONENT_DESCRIPTIVE_SET`, `c.name = $name`
silently overwrote it - every caption came out as the empty string, with no
error anywhere. Caught by running it against a real database, not by any
unit test; `tests/test_neo4j_graph_store_integration.py::
test_caption_does_not_clobber_the_dom_name_attribute` is the guard.

`:Site` is also keyed by `name`, so that property was overloaded twice over
before this.
