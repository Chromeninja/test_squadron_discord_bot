---
name: gh-pr-edit
description: "Use when updating a GitHub PR title or body and gh pr edit fails with a GraphQL deprecation error about classic Projects. Falls back to direct GraphQL mutation via gh api."
---

# gh pr edit via GraphQL API

## Overview

`gh pr edit` fails with exit code 1 on repos that use GitHub classic Projects:

```
GraphQL: Projects (classic) is being deprecated in favor of the new Projects experience
```

The fix is to call the GraphQL mutation directly via `gh api graphql`.

## When to Use

- `gh pr edit` exits 1 with the classic Projects deprecation error
- Updating PR title or body in any automated/scripted context where failure must not be silent

## Quick Reference

```bash
# 1. Get the PR node ID
PR_ID=$(gh pr view <number> --json id -q .id)

# 2. Update body via GraphQL mutation
gh api graphql -f query='
mutation {
  updatePullRequest(input: {
    pullRequestId: "'"$PR_ID"'",
    body: "'"$(cat /tmp/pr_body.md | python3 -c "
import sys
print(sys.stdin.read()
  .replace('\\\\', '\\\\\\\\')
  .replace('\"', '\\\\\"')
  .replace('\n', '\\\\n')
  .replace('\r', '\\\\r')
)")"'"
  }) {
    pullRequest { number title }
  }
}'
```

## Step-by-Step

### 1. Write body to a temp file

```bash
cat > /tmp/pr_body.md << 'EOF'
## Summary
Your PR description here...

Closes #42
EOF
```

### 2. Get the PR node ID

```bash
PR_ID=$(gh pr view <number> --json id -q .id)
```

The node ID looks like `PR_kwDOA...` — it's different from the PR number.

### 3. Escape and send the mutation

```bash
ESCAPED=$(python3 -c "
import sys
body = open('/tmp/pr_body.md').read()
print(body
  .replace('\\\\', '\\\\\\\\')
  .replace('\"', '\\\\\"')
  .replace('\n', '\\\\n')
  .replace('\r', '\\\\r')
)")

gh api graphql -f query="
mutation {
  updatePullRequest(input: {
    pullRequestId: \"$PR_ID\",
    body: \"$ESCAPED\"
  }) {
    pullRequest { number title }
  }
}"
```

### 4. Verify the update

```bash
gh pr view <number> --json body -q .body | head -5
```

## To Update Title

Add `title:` alongside `body:` in the mutation input:

```graphql
updatePullRequest(input: {
  pullRequestId: "PR_ID",
  title: "New title here",
  body: "New body here"
})
```

## Common Mistakes

- Forgetting to escape the body — newlines and quotes break the GraphQL string
- Using PR number instead of node ID — `pullRequestId` takes `PR_kwDO...`, not the integer
- Assuming `gh pr edit` exit code — the deprecation error causes exit 1, so `|| true` swallows it silently
