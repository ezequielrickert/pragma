"""`/static/*` - a small, hand-curated, exact-match set of guidance topics.

No embeddings, no vector search: per wiki/local-and-small-model-constraints.md, the real cost for
a small/CPU-bound model is prompt tokens, not retrieval sophistication, so this stays a closed
vocabulary the same way TOOL_SPECS' action verbs already are. The model requests a topic via the
`help` verb (`src/core/interfaces.py`'s TOOL_SPECS); `SimplePRDGenerator` fetches it here and
injects the text into the *next* turn's prompt only - it's meant to be consulted, not accumulated.

Keep entries short. TOOL_SPECS' one-liners are what the model pays for on every turn; these are
the fuller "why/how" it only pays for when it actually asks.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/static", tags=["static"])

TOPICS: dict[str, str] = {
    "goal_overview": (
        "You are exploring a web app to produce a PRD (Product Requirements Document) - a "
        "structured description of what the app does, its routes, and its interactive flows. "
        "Each turn you see the current page's Pending routes and Clickable elements, and choose "
        "one action. Call finish once every pending route has been explored - don't keep acting "
        "on a page you've already fully covered."
    ),
    "ref_semantics": (
        "`ref` is never a CSS selector or a name you invent - it is always one of the exact "
        "integers shown next to an element in that turn's Clickable elements list. Numbers are "
        "reassigned every turn as the page changes, so always re-read the current list before "
        "picking a ref; do not reuse a ref number from a previous turn's list."
    ),
    "navigate_usage": (
        "navigate(url) only works with a URL taken verbatim from that turn's Pending routes list "
        "- it is not a general-purpose 'go anywhere' action. Do not invent a URL or navigate to "
        "somewhere not currently listed as pending."
    ),
    "click_usage": (
        "click(ref) clicks a numbered element - use it for buttons, links, and anything without a "
        "text-input role. If the element you want is an input/textarea (check its role in the "
        "Clickable elements list), use fill instead, not click."
    ),
    "fill_submit_flow": (
        "For a text field: first fill(ref, value) to type into it, then a second action, "
        "submit(ref) on the *same* ref, to press Enter and submit. fill alone does not submit "
        "the form - you need both steps, in that order, across two separate turns. See "
        "text_field_values for how to pick `value` itself."
    ),
    "text_field_values": (
        "Before filling a text field, figure out what it's for from its label/placeholder/type "
        "shown in the Clickable elements list (e.g. \"placeholder='Email'\" or "
        "\"label='Full name'\"), then generate a realistic-looking value that fits - an email "
        "field gets something like name@example.com, a name field a plausible full name, a "
        "search box a term relevant to the page's Page context line, a phone field a "
        "plausible-looking number. Never fill a guess-free field with junk text or leave it "
        "blank if a sensible value is inferable - an empty/nonsense value in a required field is "
        "the most common reason a form fails to submit."
    ),
    "finish_criteria": (
        "Call finish only when every route listed as pending across the whole session has been "
        "visited and its interactive elements explored. Calling finish early leaves parts of the "
        "app undocumented in the final PRD; calling it too late wastes iterations re-exploring "
        "pages with nothing new to find."
    ),
    "combobox_usage": (
        "Some elements have role=option in the Clickable elements list - these are options in an "
        "already-open dropdown/combobox, not free text to describe. Click one directly by its ref "
        "instead of typing into any nearby search box - only fill that search box first if the "
        "option you actually want isn't in the currently visible list. Do not invent search terms "
        "hoping to find a specific option; check what's already shown before typing anything."
    ),
    "form_completion_flow": (
        "A page can have several fields to fill before it's ready to submit - check every visible "
        "field's `current value` in the Clickable elements list: fields already showing a value "
        "don't need refilling, fields marked `required` and showing no value still need one before "
        "submitting will work. Once every required field has a current value, click the submit "
        "button (its type is \"submit\") instead of continuing to explore or re-filling fields "
        "that already have a value."
    ),
}


@router.get("/topics")
async def list_topics() -> list[dict]:
    """Summaries for every topic - what /static/{topic} would return, in miniature."""
    return [{"topic": topic, "summary": text[:80] + ("..." if len(text) > 80 else "")} for topic, text in TOPICS.items()]


@router.get("/{topic}")
async def get_topic(topic: str) -> dict:
    if topic not in TOPICS:
        available = ", ".join(sorted(TOPICS))
        raise HTTPException(status_code=404, detail=f"Unknown topic '{topic}'. Available: {available}")
    return {"topic": topic, "content": TOPICS[topic]}
