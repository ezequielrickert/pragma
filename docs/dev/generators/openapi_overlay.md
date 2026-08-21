# `generators/openapi_overlay.py`

## module

Minimal OpenAPI Overlay Specification 1.0.0 applier - docs/adr/0004's
non-destructive redaction workflow: `openapi.raw.yaml`, an overlay of
redaction actions, applied to produce the public `openapi.yaml`.

Deliberately not a full JSONPath implementation. `redaction.overlay.yaml`
is hand-authored (`CONTEXT.md`'s Rule catalog shape: fixed for a
rule-set version, not derived from any crawl), so this only resolves the
path shapes a human actually writes for this purpose - dotted keys,
bracket-quoted keys (for a path template's own `/`, `{`, `}`), and a
`[*]` wildcard fan-out. No filter expressions, no array indices, no
recursive descent - a real JSONPath dependency for an overlay file that
ships empty by default (`config/redaction.overlay.yaml`) would be more
machinery than this v1 need justifies.

## _segments

Parses a target string into one step per path segment - `"*"` marks a
wildcard. Raises on anything this subset doesn't recognize rather than
matching nothing silently: an overlay action that never fires because its
target was mistyped is a rule someone should be told isn't working, not
one that quietly no-ops.

## _path_step

One more step of a concrete field path - dot form for an
identifier-shaped key, bracket-quoted otherwise, `[N]` for a list index.
Mirrors `_segments`'s own dot-vs-bracket split, so a concrete path this
module resolves a wildcard to reads like a target a maintainer could
have hand-written, not an internal encoding.

## _matches

`[(field_path, container, key)]` for every location a segment list
resolves to inside a document, walking recursively - a wildcard fans out
over every key of a dict or every index of a list at that level, so
`$.paths[*][*].example` reaches every operation's `example` field in one
action. `field_path` is the concrete path each match resolved to, not
the wildcard template - `apply_overlay` ignores it, `redaction_events`
is why it's threaded through at all.

## apply_overlay

Deep-copies the document first - `openapi.raw.yaml`'s own payload must
survive unchanged for its own write, since this function's result is a
different file entirely. Applies each action's matches in reverse order,
so a wildcard removing several items from the same list doesn't shift the
indices of matches still queued for deletion within that same action.

## redaction_events

Same match pass as `apply_overlay`, read-only against the pre-redaction
document instead of applying anything - `redaction_log.py`'s only way to
learn which concrete field a rule touched without ever holding the value
that was there. An action that matches nothing this run contributes no
event: a rule that never fired isn't evidence anything was redacted.
