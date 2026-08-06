---
name: wiki-update
description: Record a newly-learned, generalizable lesson into wiki/ after fixing a real bug or making an architecture decision in the LLM-driven-browser-agent problem space - especially a "looked like X, was actually Y" bug, a corrected earlier assumption, or a decision with real trade-offs (not a one-off implementation detail). Also use when the user explicitly asks to "add this to the wiki", "document this", or "record this lesson". Do NOT use for routine changelog-shaped facts (a version bump, a renamed variable) - see this skill's "What belongs here" section for the actual bar.
---

# Wiki Updater

`wiki/README.md` states the rule this skill exists to enforce: **"This is durable domain knowledge,
not a changelog."** Before adding anything, confirm what you're about to add clears that bar.

## What belongs here

A lesson belongs in the wiki if it's general enough to apply to a *different* agent, a *different*
scraper, or a *different* project in the same problem space — not just a fact about this one
codebase's current state (that's what `ARCHITECTURE.md` and code comments are for). The test used
throughout this wiki: does this entry have a concrete **symptom** (what did it look like from the
outside), a **root cause** (what was actually wrong), and a **fix pattern** (a reusable code
shape)? If you can't fill in all three, it's probably not ready yet, or it's not wiki-shaped.

## Process

1. **Identify which existing doc it belongs in**, using `wiki/README.md`'s index table (each doc's
   "Read this when..." row) the same way `wiki-context` does for consumption. Read that doc in full
   before editing it — you need to know what's already there to place the new section well and to
   catch contradictions (next step).
2. **Check whether the new lesson corrects something already written**, don't just append
   alongside it. If what you learned contradicts or supersedes existing guidance in that doc,
   *update that section in place* with an explicit callout, rather than leaving the old (now wrong)
   guidance to stand unchallenged next to a new section that quietly disagrees with it. This
   project's own wiki has two real examples to match the style of:
   - `prompt-engineering-for-llm-agents.md`, Principle 4: the original guidance ("keep a lenient
     selector fallback for clever models") was later found to be actively wrong and reversed - the
     correction is inline, prefixed `**Update — the literal-selector fallback below was later
     removed, on purpose:**`, explaining what changed and why, right where the old guidance was.
   - `graph-based-crawl-tracking.md`'s "Prefer decline over override" section: a later, narrower
     exception to the original "override is risky" stance was added as `**Update — one narrow,
     later-added exception, and why it's different...**`, explicitly reconciling the new case with
     the original rule rather than contradicting it silently.
3. **If it doesn't fit any existing doc's stated scope**, only then consider a new file — this is
   the exception, not the default. `tool-calling-and-execution-layers.md` was added this way,
   because the material (native tool-calling reliability *as a transport/execution-design concern*,
   standing-service lifecycle) didn't fit the scope statement of any of the five docs that existed
   before it. A new file needs the same scope-statement-first structure as the others (see
   "Format" below) and **must** be added to `wiki/README.md`'s index table and, if it covers a new
   symptom shape, the "Quick symptom → doc lookup" list.
4. **Verify internal links** after editing - every `[text](some-file.md)` must resolve to a real
   file in `wiki/`. Check with a quick scan, not by assumption:
   ```bash
   grep -oh '\]([a-zA-Z0-9_.-]*\.md)' wiki/*.md | sed 's/](//; s/)//' | sort -u
   ```
5. **Cross-reference, don't duplicate.** If a related point is already made in another doc, link to
   it (`see [other-doc.md](other-doc.md)`) instead of re-explaining it - this wiki consistently
   cross-links rather than repeating itself across files.

## Format

Match the existing terse, symptom-driven style exactly - every doc opens with a one-paragraph scope
statement ("Applies to/whenever..."), then `##`-level sections shaped like:

```markdown
## Short, specific section title naming the pattern, not just "Bug fix"

**Symptom observed**: what it looked like from the outside - the literal error text or observed
behavior, specific enough that someone hitting the same symptom recognizes it immediately.

**Why it happens**: the mechanism (optional - include when the "why" isn't obvious from the fix).

**Fix pattern**: the reusable shape of the fix, with a short code block showing it concretely -
not a description of what to do in prose alone.
```

Keep code blocks short and illustrative, not a full diff - enough to show the *shape* of the fix,
matching how every existing entry does it. Write in the same voice as the rest of the file you're
editing (check it before writing, they're not identical file to file).

## After updating

Tell the user which file(s) changed and, in one line each, what was added or corrected - don't
just say "updated the wiki." If you updated (not just appended to) an existing section per step 2,
say so explicitly, since that's the part most likely to matter to someone who already knew the old
guidance.
