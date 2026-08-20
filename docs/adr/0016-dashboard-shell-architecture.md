# The dashboard is a static site, landing on a metrics-first status board

**Status**: accepted

The format audit calls for a single interactive entry point replacing the 9+ separate `.md` views
every document currently gets, but leaves the shell's technology, build sequence, and layout open.
This ADR locks all three, resolved through `grilling` for the architecture and `prototype` for the
shell's actual shape — four structurally different layouts were built and reacted to live before
converging on the winner.

Decided, resolving the ticket's three open points plus the shell layout itself:

**1. Tech Choice: Static Site, No Server, No Build Step.** Python emits self-contained static HTML
at doc-generation time. Forced, not merely preferred, by the ticket's own stated audience — "a human
reviewer and Claude Code itself," not a public-facing product. Claude Code consuming the dashboard
means reading files directly; that works against static HTML with content already in the page, but
not against an SPA whose `index.html` is an empty `<div id="root">` until a browser executes JS. A
server-rendered option adds a live process nothing else in this batch crawl-then-generate pipeline
needs. Confirmed against the existing codebase: zero web or templating dependencies in
`requirements.txt`, every current `.md` generator (`generators/*.py`) already builds Markdown via
plain Python string formatting — this decision extends an existing convention, not replaces one.

**2. Phase A/B/C Build Plan.** (A) Every document becomes a typed source, no viewer — the state
every ticket in this map up through `#79` has already produced. (B) A per-document renderer wins
over the shared generic template only when it clears a real bar: ships as a single vendorable static
asset consumable via one `<script>`/`<link>` tag with no Node.js toolchain required to *use* it
(Redoc's `redoc.standalone.js` is the reference case — its own upstream build process is irrelevant,
only what pragma has to run to embed it), is actively maintained, and saves meaningfully more effort
than the generic template. Everything else defaults to the generic template. (C) All of it stitched
behind the shell locked in point 4, below.

**3. Phase B Renderer-Selection Criteria.** Locked as criteria only (point 2), not a per-document
assignment — auditing all ~15 documents against this bar is Phase B's own implementation work, not a
decision this ticket needs to pre-empt.

**4. Shell Layout: Landing Grid, No Persistent Nav Chrome.** Four variants were prototyped and
reacted to live (see the throwaway branch, below): (A) a persistent sidebar tree; (B) top concern
tabs with a secondary source/view tab row; (C) a landing page — crawl-wide metrics first, a card
grid of every concern second, each card drilling into its own detail page, no sidebar or top bar
shown everywhere; (D) a hybrid, A's persistent sidebar wrapped around C's card/KPI visual language.
**C won.** The landing page carries the navigation rather than a chrome element repeated on every
screen — consistent with a dashboard whose primary read is "what's the state of things," not
"drill three levels into a tree." Landing page content, top to bottom:

- **Crawl-wide metrics** (new to this ticket, requested during prototype review): pages crawled vs.
  found, components interacted with vs. discovered, requirement confidence split
  (`observed`/`inferred`/`assumed`, `prd`'s ADR-0009 vocabulary), and endpoint count — shown as a
  saturating count, not a forced fraction, since `coverage`'s ADR-0001 deliberately gave endpoints no
  denominator ("a saturation curve, no denominator needed"). A metric locked elsewhere in this map
  never gets reshaped into a shape that ADR didn't choose.
- **A card per concern**, each showing its own coverage/confidence at a glance and linking through to
  a dedicated page listing that concern's source(s), view, and projection (where it has one).

**Prototype**: [`prototype/dashboard-80`](https://github.com/ezequielrickert/pragma/tree/prototype/dashboard-80)
(throwaway branch, not merged — captures all four variants and the switcher as the primary source of
this decision, per the `prototype` skill).

Wayfinder ticket: [dashboard: decide shell architecture and rendering strategy](https://github.com/ezequielrickert/pragma/issues/80),
part of [Doc-generation pipeline overhaul](https://github.com/ezequielrickert/pragma/issues/64).
