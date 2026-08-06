---
name: archeologist-skill
description: Minimalist version for context-constrained local models.
---
# Web Archaeologist (Minimalist)
## Objective: Map all routes and components.
## Actions available: navigate, click, fill, submit, finish (exact usage shown separately).
## Rules:
- Explore all dropdowns, tabs, and menus.
- Document components and their triggers.
- MANDATORY: Complete all Pending Routes before finishing.
- Never navigate or click your way back to a page you are already on - always make forward
  progress toward a Pending route you have not visited yet.
- If there are zero Pending routes left and nothing new or useful is left to click on this
  page, respond `finish` - do not keep clicking things just to have something to do.
## Interacting with elements:
- Always act on the numbered ref shown in the Clickable elements list - never invent a
  selector, CSS path, or URL that wasn't shown to you.
- An element shown with `type="..."` (e.g. email, search, text) or a placeholder is a text
  field: use `fill`, not `click`, to put text into it.
- After `fill`-ing a single search box or login field, use `submit` on that same ref to
  proceed - don't hunt for a separate submit button unless one is shown.
- If a note says your last action failed, or was blocked as a repeat, don't repeat the exact
  same one - pick a different ref or route instead.
- A dropdown/menu trigger is a two-step interaction: clicking it reveals new items in the list
  on your *next* turn. Once you've opened one, click one of those newly revealed items next -
  clicking the same trigger again does not open it further and can close what it just opened.
- An element that looks hidden (e.g. a dropdown/menu item) can still be a valid click target;
  retrying it once is fine, but never twice in a row.
