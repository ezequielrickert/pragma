---
name: dev-trunk-flow
description: This repo's mandatory git workflow around any ticket/issue implementation - pull dev, branch, implement, merge straight back to dev with no PR, keep main untouched. Trigger automatically and silently (no need for the user to name this skill) on ANY request to implement, start, work on, resolve, pick up, tackle, continue, or finish a ticket/issue in this repo - including a wayfinder ticket, a bare issue number ("do #49", "let's do 49"), or "next ticket"/"keep going" once a map is already in play. Also covers "merge to dev" and "promote dev to main".
---

# Dev trunk flow

`dev` is this repo's trunk: short-lived, fast, always-moving. `main` is the stable snapshot -
it only moves when someone deliberately promotes it, never per-ticket. No PR opens against
`dev` for ordinary ticket work; a PR is the overhead this flow exists to skip. (A PR is still
the right tool for `dev` → `main` promotion, or for a change that genuinely wants review before
landing - this flow is for the common case, not a ban on PRs.)

Pairs with [[wayfinder]]: this covers the git mechanics of one ticket's implementation session;
wayfinder covers claiming the ticket, resolving it, and recording the resolution on the map.
Run this flow's steps 1-2 right after claiming a ticket, and step 4 as part of wayfinder's own
"record the resolution" step, not after it - the merge and the resolution comment happen
together, since the merge commit is what the resolution comment points at.

## 1. Sync dev

Before anything else, make local `dev` match `origin/dev` exactly - every ticket starts from the
latest trunk, not from whatever a previous session happened to leave checked out.

```bash
git fetch origin
git checkout dev
git merge --ff-only origin/dev
```

`--ff-only` is deliberate: if this fails, `dev` has local commits that never got pushed - stop
and reconcile that before starting new work, don't silently diverge further.

## 2. Branch per ticket

One short-lived branch per ticket, cut from `dev`, named `<issue-number>-<slug>` (e.g.
`49-pragma-dynamic`) so the branch name alone says which ticket it's for.

```bash
git checkout -b 49-pragma-dynamic dev
```

Implement the ticket on this branch as normal - the existing code-quality pipeline (CLAUDE.md),
tests, commits, all apply unchanged. Commit as many times as the work naturally wants; this
branch never gets force-pushed or rewritten; it's a scratch surface for one ticket, not a
shared branch.

## 3. Merge back to dev - no PR

Once the ticket's work is done and tested, merge directly:

```bash
git checkout dev
git merge --ff-only origin/dev   # catch anyone else's merge since step 1
git merge --no-ff 49-pragma-dynamic -m "Merge 49-pragma-dynamic: <ticket title> (resolves #49)"
git push origin dev
```

`--no-ff` is deliberate, even though a fast-forward would often work: a real merge commit is
this flow's *only* audit trail once the ticket branch is deleted (step 4) and no PR exists to
browse later - `git log --oneline --merges dev` has to be able to answer "which commit was
ticket #49" on its own. The merge commit message is the one place that mapping is guaranteed to
live, so always spell out `resolves #N` in it, not just the ticket title.

If the merge conflicts, resolve the same way any merge does: fix what's genuinely conflicting,
prefer whichever side's intent is clearer for anything ambiguous, and ask the user before
resolving anything that reads as a design decision rather than a mechanical reconciliation - see
[[wayfinder]] for that same judgment call at the ticket-resolution level.

## 4. Clean up and record

```bash
git branch -d 49-pragma-dynamic
git push origin --delete 49-pragma-dynamic   # only if it was ever pushed
```

Then do wayfinder's own "record the resolution" step (resolution comment on the ticket, close
it, append to the map's Decisions-so-far) - link the merge commit (`dev@<short-sha>` or the
GitHub commit URL) the same way a PR link would normally be cited, since that commit is what
carries the "which ticket, which changes" mapping once the branch is gone.

## Promoting dev to main

Not part of the per-ticket loop - a deliberate, separate act, done when `dev` is in a state
worth calling stable. Ask the user before doing this rather than deciding on your own that
`dev` is ready; "stable enough to promote" is a judgment this flow doesn't make unilaterally.
When asked to promote:

```bash
git checkout main
git merge --ff-only origin/main
git merge --no-ff dev -m "Promote dev to main: <one-line summary of what's landing>"
git push origin main
```

`main` never receives anything else - no per-ticket merges, no direct commits, no hotfixes
landed straight there. If `main` needs a fix that can't wait for the next promotion, branch the
fix from `main`, land it there directly, then merge `main` back into `dev` so trunk doesn't
silently diverge from the branch it's supposed to be ahead of.
