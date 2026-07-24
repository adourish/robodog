---
name: gitflow-workflow
description: Apply the Gitflow branching workflow to any project. Use when starting new work, merging a feature, cutting a release, or hotfixing production. Covers feature -> dev -> main flow, branch naming, commit conventions, merge discipline, and PR/MR process for both GitHub (robodog) and FDA GitLab (SERIO+ repos).
metadata:
  version: "1.0.0"
  runtime: prompt
---

# Skill: gitflow-workflow

Apply the Gitflow branching model consistently across all projects.

---

## Branch model

```
main          ← production-ready; tagged releases only
  └── dev     ← integration branch; all features land here first
        └── feature/<ticket-or-slug>   ← one branch per feature/fix
        └── feature/<TICKET>-<slug>    ← with a ticket number
        └── bugfix/<slug>              ← bug fixes off dev
  └── hotfix/<slug>                    ← emergency fixes off main; merge to main AND dev
  └── release/<version>               ← release stabilisation off dev
```

### Branch rules

| Branch | Branch from | Merge to | Protected | Who merges |
|--------|------------|----------|-----------|------------|
| `main` | — | — | ✅ Yes | Maintainer only; via PR/MR |
| `dev` | `main` | `main` | ✅ Yes | Maintainer; via PR/MR |
| `feature/*` | `dev` | `dev` | No | Author; PR/MR required |
| `bugfix/*` | `dev` | `dev` | No | Author; PR/MR required |
| `release/*` | `dev` | `main` + `dev` | No | Maintainer |
| `hotfix/*` | `main` | `main` + `dev` | No | Maintainer |

---

## Starting new work

```bash
# Always branch from dev
git checkout dev
git pull origin dev

git checkout -b feature/<ticket>-<slug>
# e.g.:
git checkout -b feature/SERIO-39310-seizure-memo-pdf
git checkout -b feature/gitflow-skill
git checkout -b bugfix/gateway-jar-not-found
```

---

## Daily workflow

```bash
# 1. Work on your feature branch
git add <files>
git commit -m "feat(scope): short description"

# 2. Keep up to date with dev
git fetch origin
git rebase origin/dev     # preferred over merge to keep history clean

# 3. Push
git push origin feature/<name>
```

---

## Commit message convention (Conventional Commits)

```
<type>(<scope>): <short description>

[optional body]

[optional footer: Co-Authored-By, Closes #N]
```

| Type | When |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `chore` | Build, tooling, dependencies |
| `refactor` | Code change that is not a fix or feature |
| `test` | Adding or fixing tests |
| `perf` | Performance improvement |
| `ci` | CI/CD configuration |

Examples:
```
feat(serioplus): add seizure memo PDF endpoint
fix(gateway): build local-gateway-service separately from reactor
docs(whitepaper): add AOA for LLM agentic clients
chore: bump robodog-terminal to 0.3.79
```

---

## Finishing a feature — PR/MR to dev

### GitHub (robodog, ai-sdlc-playbook mirror)

```bash
git push origin feature/<name>
gh pr create \
  --base dev \
  --title "feat: <description>" \
  --body "## What\n\n<description>\n\n## How tested\n\n<steps>\n\n🤖 Generated with Claude Code"
```

### FDA GitLab (SERIO+ repos)

```bash
git push origin feature/<name>
# GitLab prints the MR creation URL in the push output:
# remote: To create a merge request, visit:
# remote:   https://git.fda.gov/.../merge_requests/new?...
```

Or create via the GitLab API (gitlab-call skill):
```python
mod.create_merge_request(
    project_id=7255,               # SERIOPlusDataServices
    source_branch="feature/SERIO-39310",
    target_branch="dev",
    title="feat(SERIO-39310): seizure memo PDF endpoint",
    description="...",
)
```

---

## Merging dev → main (release)

```bash
git checkout main
git pull origin main
git merge --no-ff dev -m "release: <version>"
git tag -a v<version> -m "Release <version>"
git push origin main --tags

# Back-merge to dev
git checkout dev
git merge --no-ff main
git push origin dev
```

---

## Hotfix (production bug)

```bash
# Branch from main, not dev
git checkout main
git pull origin main
git checkout -b hotfix/<slug>

# Fix, commit, push
git commit -m "fix: <description>"
git push origin hotfix/<slug>

# PR to main
# After merge to main, also merge to dev:
git checkout dev
git merge --no-ff main
git push origin dev
```

---

## Branch naming cheat sheet

```
feature/SERIO-39310-seizure-memo-pdf    ticket + slug
feature/gitflow-skill                   slug only (no ticket)
bugfix/gateway-jar-not-found            bug fix
hotfix/pdf-crash-on-null-lines          production hotfix
release/1.1.0                           release branch
```

Rules:
- All lowercase, hyphens only (no underscores, no spaces)
- Include ticket number when one exists: `feature/SERIO-39310-<slug>`
- Keep slugs short (3-5 words max)

---

## Project-specific notes

### robodog (`github.com/adourish/robodog`)
- Default branch: `main`
- Integration branch: `dev` (tracked as `origin/develop` — push to `origin dev`)
- Feature branches: `feature/*` off `dev`
- Hotfix: `hotfix/*` off `main`

```bash
# Start work
git checkout dev && git pull origin dev
git checkout -b feature/<slug>

# Finish
git push origin feature/<slug>
gh pr create --base dev ...
```

### SERIO+ repos (FDA GitLab `git.fda.gov`)
- Mirror: GitHub `github.com/adourish/<repo>`
- Default branch: `main`
- Integration branch: `dev`
- Feature branches: `feature/<TICKET>` or `feature/<TICKET>-<slug>`
- **Push to GitHub** (`git push github HEAD`) — GitLab push requires Maintainer for protected branches

```bash
# Start work
git checkout dev && git pull github dev
git checkout -b feature/SERIO-XXXXX-slug

# Push
git push github HEAD
```

### ai-sdlc-playbook (`git.fda.gov/FDA/ORA/SI/ai-sdlc-playbook`)
- Integration branch: `dev`
- Feature branches: `feature/<slug>`
- Push directly to `origin dev` for docs/skills/runbooks

---

## Common mistakes and fixes

| Mistake | Fix |
|---------|-----|
| Branched from `main` instead of `dev` | `git rebase --onto dev main feature/<name>` |
| Committed directly to `dev` | Create a feature branch, cherry-pick the commits |
| Forgot to pull `dev` before branching | `git rebase origin/dev` before pushing |
| Merge commit instead of rebase | `git rebase -i origin/dev` to clean up |
| Pushed to `main` directly | Revert on `main`; apply to `dev` via feature branch |
| Branch name has uppercase | Rename: `git branch -m feature/My-Feature feature/my-feature` |

---

## Related

- `docs/runbooks/RUNBOOK-gitflow-workflow.md` — step-by-step command reference
- `skills/gitlab-call/SKILL.md` — create MRs programmatically on FDA GitLab
- `skills/session-handoff/SKILL.md` — hand off work between sessions with branch state
