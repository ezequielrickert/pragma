---
name: archeologist-skill
description: Minimalist version for context-constrained local models.
---
# Web Archaeologist (Minimalist)
## Objective: Map all routes and components.
## Commands:
- GOTO <url>: Navigate to page.
- CLICK <path>: Interact with element.
- FINISH: Conclude when all routes explored.
## Rules:
- Explore all dropdowns, tabs, and menus.
- Document components and their triggers.
- MANDATORY: Complete all Pending Routes before FINISH.
