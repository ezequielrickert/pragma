# Git Workflow

`dev` is trunk: short-lived branch per ticket, implement, merge straight back to `dev` with no
PR. `main` is the stable snapshot, only updated by deliberate promotion. See
`.claude/skills/dev-trunk-flow/SKILL.md` (locally authored, not upstream-tracked) for the exact
steps.

**This is not optional and does not need to be asked for by name.** Any request to implement,
start, work on, resolve, pick up, or continue a ticket/issue in this repo — a wayfinder ticket,
a bare issue number, or "next ticket"/"keep going" — invokes `dev-trunk-flow` with the `Skill`
tool automatically, before touching any code, the same way the code-quality pipeline below runs
without being asked for by name. Never implement ticket work directly on `main`, `dev`, or
whatever branch happens to be checked out — always cut this ticket's own branch first. When the
ticket is a wayfinder ticket, run `dev-trunk-flow` and `wayfinder` together: `dev-trunk-flow`
owns the git mechanics (sync, branch, merge, promote), `wayfinder` owns claiming the ticket and
recording its resolution — do not substitute one for the other.

# Code Quality Pipeline

Three quality skills are installed under `.claude/skills/` (mirrored from `.agents/skills/`,
where a separate skill-lock tool tracks their upstream sources — see `skills-lock.json`):

- **python-clean-code** — Robert Martin's Clean Code catalog adapted for Python (naming,
  functions, comments, boundary conditions).
- **clean-code-principles** — SOLID, DRY, KISS, YAGNI, and the repository pattern,
  language-agnostic.
- **anti-slop** — catches generic AI-generated patterns in code, prose, and design
  (placeholder names, obvious comments, buzzword-y copy, template-driven structure).
- **file-size-audit** — flags source files past 300/500/700 lines as SRP-split candidates
  (locally authored, not upstream-tracked — see `.claude/skills/file-size-audit/SKILL.md`).

Run them as a pipeline whenever a task involves writing or editing source code, not just at
the end of a big feature:

1. **While writing Python** (`core/`, `agents/`, `database/`, `spiders/`, `generators/`,
   `utils/`, `tests/`, any `.py` file) — apply `python-clean-code`
   as you go: max 3 function args, no output args, no flag args, no dead code, no
   commented-out code.
2. **Before presenting a diff or finishing a code task** — run `clean-code-principles`
   against the changed files: check for SRP/DIP violations, duplicated logic (DRY),
   overengineering (YAGNI), and unclear composition. Language-agnostic, so apply it to
   non-Python changes too (configs, scripts, docs generators). If the edit grew a file past
   300 lines, or touched a file already there, run `file-size-audit` too — an OVERLOADED
   result feeds back into the SRP check rather than standing alone.
3. **Final pass before showing the result** — run `anti-slop` over both the code and any
   prose written in the same task (commit messages, docstrings, generated docs, PRDs).
   Reject generic names (`data`, `result`, `temp`), restating comments, and filler phrases
   ("it's important to note that", "leverage", "delve into").

Invoke each skill by name with the `Skill` tool (`python-clean-code`, `clean-code-principles`,
`anti-slop`, `file-size-audit`) rather than re-deriving these rules from memory — the skill
files hold the concrete bad/good examples, rule IDs (e.g. `solid-srp-class`, `core-dry`), and
thresholds to cite in findings.

Skip the pipeline only for changes that touch no source code or generated prose (e.g. a pure
data file, a `.gitignore` entry).
