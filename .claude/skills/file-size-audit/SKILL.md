---
name: file-size-audit
description: Scan source files for line-count overload, then confirm each candidate against the clean-code-principles SRP check before proposing a split. Use when checking file/module size, hunting for files to refactor or split, or as part of the code-quality pipeline before finishing a code task that touched a large file.
---

# File Size Audit

A large file is usually a symptom, not the disease — past a few hundred lines a module has
almost always picked up more than one responsibility. This skill turns "seems like an
overload" into a number and a threshold, then hands the actual fix to
[[clean-code-principles]] (`solid-srp-class`, `org-module-boundaries`) and
[[python-clean-code]] (G30: functions do one thing) rather than reinventing that guidance.

## Thresholds

| Lines | Status | Meaning |
|-------|--------|---------|
| < 300 | OK | No action |
| 300–499 | WATCH | Note it; split only if responsibilities are already visibly mixed |
| 500–699 | SPLIT | Look for a seam — the file is doing more than one job |
| 700+ | OVERLOADED | Don't add more to this file until it's split |

These count raw lines (including blanks/comments) via `wc -l`-equivalent counting — close
enough for triage. Don't chase the number itself; use it to decide which files are worth a
closer SRP read.

## Running the audit

```bash
python3 .claude/skills/file-size-audit/scripts/loc_report.py           # scans src/ and tests/
python3 .claude/skills/file-size-audit/scripts/loc_report.py src       # one root
python3 .claude/skills/file-size-audit/scripts/loc_report.py --fail-over 700   # exit 1 if any file trips the OVERLOADED line
```

Output is one line per file, sorted largest-first, with a `[WATCH]` / `[SPLIT]` /
`[OVERLOADED]` marker past each threshold.

## When a file trips SPLIT or OVERLOADED

A line count alone doesn't prove an SRP violation — it's a prompt to go check for one. Don't
stop at the number:

1. Invoke the `clean-code-principles` skill (via the `Skill` tool) and run its SRP-class
   check (`solid-srp-class`) against the flagged file specifically — not the whole diff.
   That's the actual test of "overloaded": does the file have more than one reason to
   change?
2. If that check finds a single responsibility just implemented at length (e.g. one big
   state machine, one large parser), the file is long, not overloaded — leave it, and say
   so rather than forcing a split for the sake of the line count.
3. If it finds two or more responsibilities, list them and, for each, check whether it
   already maps to a class/function group that could move to its own module.
4. Propose the split (new file names + what moves), citing the specific `solid-srp-class`
   violation for each piece — this skill flags candidates and confirms them via the SRP
   check, it doesn't apply the refactor itself.

## When to run this

- As part of the [[clean-code-principles]] pass in the project's code-quality pipeline
  (see `CLAUDE.md`), whenever a task edits a file that's already near a threshold or grows
  one past it.
- On request: "which files are too big", "find refactor candidates", "check file sizes".

Not a gate on every commit — a single large data file or generated module isn't a code
smell just because `wc -l` is high; use judgment on what `--ext` and `roots` you point it at.
