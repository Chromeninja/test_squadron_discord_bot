---
name: github-issue-tracking
description: "Step-by-step guide for creating and managing GitHub Issues, Milestones, and Project boards using the gh CLI. Use when creating issues, milestones, setting up project boards, listing open work, or managing issue ownership for this Discord bot project."
---

# GitHub Issue Tracking

## When to Use

- Creating a new issue, feature request, bug report, or chore
- Creating or updating a milestone
- Listing open issues or milestone status
- Assigning, reassigning, or querying issue ownership
- Setting up a GitHub Projects board

## Step 0: Pre-Flight Check

```bash
gh --version || echo "NOT INSTALLED"
gh auth status
gh repo view --json nameWithOwner -q .nameWithOwner
```

## Process 1: Create a New Issue

### 1a. Check for duplicates

```bash
gh issue list --search "<short description>" --state open
```

If a match exists, return its number and stop.

### 1b. Create the issue

```bash
gh issue create \
  --title "[Feature] Short imperative description" \
  --body "$(cat <<'EOF'
## User Story
As a [role], I want [capability] so that [benefit].

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Tests pass (unit + integration)
- [ ] Ruff lint passes
- [ ] mypy type check passes

## Notes
Additional context.
EOF
)" \
  --assignee @me \
  --label "type:feature,priority:medium,status:ready,component:bot-core"
```

### Required Labels

| Dimension | Values |
|-----------|--------|
| **Type** (one) | `type:feature` `type:bug` `type:chore` `type:docs` `type:security` |
| **Priority** (one) | `priority:critical` `priority:high` `priority:medium` `priority:low` |
| **Status** | `status:ready` `status:in-progress` `status:blocked` `status:review` |
| **Component** (one+) | `component:verification` `component:voice` `component:admin` `component:metrics` `component:tickets` `component:web-dashboard` `component:database` `component:config` `component:bot-core` |
| **Size** (optional) | `size:xs` `size:s` `size:m` `size:l` `size:xl` |

## Process 2: Claim / Reassign an Issue

### Check current assignee

```bash
gh issue view <N> --json assignees -q '.assignees[].login'
```

### Assign if unassigned

```bash
gh issue edit <N> --add-assignee @me
```

### Ownership conflict — reassign (only after user confirms)

```bash
gh issue edit <N> \
  --remove-assignee <previous-username> \
  --add-assignee @me
```

## Process 3: Update Issue Status

```bash
# Mark in-progress
gh issue edit <N> \
  --remove-label "status:ready" \
  --add-label "status:in-progress"

# Mark in review (when PR opened)
gh issue edit <N> \
  --remove-label "status:in-progress" \
  --add-label "status:review"
```

## Process 4: Link PRs to Issues

Every PR body MUST contain `Closes #<issue-number>`:

```bash
gh pr create \
  --title "[Feature] Add verification timeout (#42)" \
  --body "Closes #42

## Changes
- Added timeout logic
- Added tests
" \
  --assignee @me
```

## Rules

- ✅ Auto-assign to creator (`--assignee @me`)
- ✅ Check for duplicates before creating
- ✅ Close issues via PR merge with `Closes #N` — never close manually
- ✅ Check if already assigned before claiming
- ❌ Never create without labels (type + priority required)
- ❌ Never assign more than one person per issue
