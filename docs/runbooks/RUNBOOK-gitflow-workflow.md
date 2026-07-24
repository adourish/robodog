# RUNBOOK -- Gitflow Workflow

Step-by-step git commands for the Gitflow branching model used across all projects
(robodog, SERIO+, ai-sdlc-playbook).

---

## Branch model at a glance

```
main     ← production; tagged releases only; never commit directly
  dev    ← integration; all features land here first; never commit directly
    feature/<name>   ← your work lives here
    bugfix/<name>    ← bug fixes
  hotfix/<name>      ← emergency fix off main (rare)
  release/<version>  ← release stabilisation off dev (optional)
```

---

## Start new work

```bash
# 1. Make sure dev is current
git checkout dev
git pull origin dev          # or: git pull github dev (for SERIO+ repos)

# 2. Branch from dev
git checkout -b feature/SERIO-39310-seizure-memo
# or without a ticket:
git checkout -b feature/gitflow-skill
```

---

## Work on your feature

```bash
# Stage and commit often
git add <files>
git commit -m "feat(scope): description"

# Stay current with dev (rebase preferred -- keeps history linear)
git fetch origin
git rebase origin/dev

# Push your branch
git push origin feature/<name>
# SERIO+ repos push to GitHub mirror:
git push github feature/<name>
```

---

## Commit message format

```
feat(serio): add seizure memo PDF endpoint
fix(gateway): build local-gateway-service separately from reactor
docs: add gitflow workflow skill and runbook
chore: bump version to 0.3.80
refactor(parser): extract tool-call builder
test(bench): add ELSA single-task scenario
```

Types: `feat` `fix` `docs` `chore` `refactor` `test` `perf` `ci`

---

## Open a pull / merge request

### GitHub (robodog, mirrored SERIO+ repos)

```bash
# Push branch first
git push origin feature/<name>   # or: git push github feature/<name>

# Open PR targeting dev
gh pr create \
  --base dev \
  --title "feat: your description" \
  --body "## What

Short description of what changed.

## How tested

Steps to verify.

Co-Authored-By: Claude <noreply@anthropic.com>
🤖 Generated with Claude Code"
```

### FDA GitLab (SERIO+ repos on git.fda.gov)

```bash
git push origin feature/<name>
# GitLab prints the MR URL in push output -- click it
# Or open: https://git.fda.gov/FDA/ORA/SI/<repo>/-/merge_requests/new
```

---

## Merge feature → dev (after PR approved)

```bash
# Via GitHub UI / GitLab UI (preferred -- triggers CI, records reviewer)
# Use "Squash and merge" for a clean history, or "Merge commit" to keep all commits

# Or locally (maintainer only):
git checkout dev
git pull origin dev
git merge --no-ff feature/<name> -m "feat: description"
git push origin dev
git branch -d feature/<name>
git push origin --delete feature/<name>
```

---

## Merge dev → main (release)

```bash
git checkout main
git pull origin main

git merge --no-ff dev -m "release: v1.1.0"

git tag -a v1.1.0 -m "Release 1.1.0"
git push origin main --tags

# Back-merge to dev (keeps dev in sync)
git checkout dev
git merge main
git push origin dev
```

---

## Hotfix (production bug -- rare)

```bash
# Branch from MAIN, not dev
git checkout main
git pull origin main
git checkout -b hotfix/fix-pdf-crash

# Fix the bug
git commit -m "fix: handle null line keys in PDF generation"
git push origin hotfix/fix-pdf-crash

# PR to main
gh pr create --base main --title "fix: handle null line keys"

# After merge to main -- also apply to dev
git checkout dev
git pull origin dev
git merge --no-ff main
git push origin dev

# Cleanup
git branch -d hotfix/fix-pdf-crash
git push origin --delete hotfix/fix-pdf-crash
```

---

## Check branch status

```bash
# What branch am I on?
git branch --show-current

# How far ahead/behind dev am I?
git fetch origin
git rev-list --left-right --count origin/dev...HEAD

# Is my branch up to date with dev?
git log origin/dev..HEAD --oneline         # commits I have that dev doesn't
git log HEAD..origin/dev --oneline         # commits dev has that I don't

# All branches
git branch -a
```

---

## Sync with dev (rebase)

```bash
git fetch origin
git rebase origin/dev

# If conflicts:
# 1. Fix the conflict in the file
# 2. git add <file>
# 3. git rebase --continue
# Or abandon: git rebase --abort
```

---

## Branch naming rules

```
feature/SERIO-39310-seizure-memo-pdf   ← ticket + slug (preferred)
feature/gitflow-skill                  ← slug only (no ticket)
bugfix/gateway-jar-not-found           ← bug fix off dev
hotfix/pdf-null-crash                  ← production hotfix off main
release/1.1.0                          ← release branch off dev
```

- All **lowercase**, hyphens only
- Include ticket number when one exists
- Keep slugs short (3-5 words)

---

## Project remotes cheat sheet

| Repo | Push to | Branch |
|------|---------|--------|
| `robodog` | `origin` (GitHub) | `feature/*` → `dev` → `main` |
| `SERIOPlusDataServices` | `github` (GitHub mirror) | `feature/*` → `dev` |
| `SERIOPlusServices` | `github` | `feature/*` → `dev` |
| `SERIOPlusApp` | `github` | `feature/*` → `dev` |
| `SERIOPlusCommonLibraries` | `github` | `feature/*` → `dev` |
| `ai-sdlc-playbook` | `origin` (GitLab) | `feature/*` → `dev` → `main` |

---

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Branched from `main` instead of `dev` | `git rebase --onto dev main feature/<name>` |
| Committed directly to `dev` | `git checkout -b feature/fix` then `git cherry-pick <commits>` |
| Forgot to `git pull dev` before branching | `git fetch origin && git rebase origin/dev` |
| Pushed sensitive data | `git reset --hard HEAD~1 && git push --force` (before anyone pulls) |
| Need to undo last commit (local only) | `git reset --soft HEAD~1` |
| Branch name has spaces/caps | `git branch -m feature/Old-Name feature/old-name` |
| PR merged to `main` instead of `dev` | Revert on `main`, cherry-pick to `dev` |

---

## Related

- `docs/skills/gitflow-workflow/SKILL.md` -- full skill reference
- `ai-sdlc-playbook/skills/gitlab-call/SKILL.md` -- create MRs via API
