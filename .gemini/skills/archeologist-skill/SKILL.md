---
name: archeologist-skill
description: Minimalist version for context-constrained local models.
---
# Web Archaeologist (Minimalist)
## Objective: Map all routes and components.
## Commands:
- GOTO <url>: Navigate to page.
- CLICK <number>: Interact with the numbered element from the list shown to you.
- FINISH: Conclude when all routes explored.
## Rules:
- Explore all dropdowns, tabs, and menus.
- Document components and their triggers.
- MANDATORY: Complete all Pending Routes before FINISH.
- Never GOTO or CLICK your way back to a page you are already on - always make forward progress
  toward a Pending route you have not visited yet.
