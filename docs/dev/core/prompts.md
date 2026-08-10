# `src/core/prompts.py`

## module

Uses `questionary` for arrow-key select menus and edit-in-place
text/password fields when attached to a real terminal; otherwise falls
back to plain `input()` so non-interactive contexts (scripts, tests, CI)
never hang.
