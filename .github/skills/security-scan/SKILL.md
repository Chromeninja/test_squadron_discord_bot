---
name: security-scan
description: "Use when preparing to commit code, when dependencies change, or when security validation is needed. Runs Ruff bandit rules, dependency audit, and secret detection for this Python Discord bot project."
---

# Running Security Scans

## Overview

Every commit must pass security scanning. This project uses Ruff's built-in bandit rules (S prefix) and pip-audit for dependency checking.

## When to Use

- Before every commit (part of pre-commit checklist)
- After adding or updating dependencies in `requirements.txt` or `pyproject.toml`
- When asked to run a security scan or audit
- Before any deployment

## Process

### Step 1: Run Ruff Security Rules (Bandit)

```bash
ruff check --select S .
```

This runs all bandit-equivalent security checks:
- `S101` — assert usage
- `S105`/`S106`/`S107` — hardcoded passwords/credentials
- `S108` — insecure temp file usage
- `S110` — try/except/pass (swallowed exceptions)
- `S301`/`S302` — pickle usage
- `S307` — `eval()` usage
- `S603`/`S607` — subprocess with `shell=True`

### Step 2: Dependency Vulnerability Check

```bash
pip-audit
```

Checks all installed packages against known vulnerability databases. Do NOT commit if vulnerabilities are found — update the affected packages first.

### Step 3: Scan for Hardcoded Secrets

```bash
git diff --cached | grep -iE 'password|secret|key|token|credential|api_key'
```

Review any matches manually. False positives are common (e.g., variable names like `token_manager`) but each must be verified.

### Step 4: Verify Config Files

Ensure sensitive files are in `.gitignore`:
- `config.yaml` (contains Discord token, API keys)
- `.env` / `.env.local`
- `*.key` / `*.pem`

```bash
git status --ignored | grep -E 'config\.yaml|\.env'
```

### Step 5: Evaluate Results

- **Any vulnerability found = BLOCK the commit**
- Fix all issues before proceeding
- Document vulnerability fixes in the commit message if applicable

## Quick Reference

| Check | Command | What it catches |
|-------|---------|-----------------|
| Bandit rules | `ruff check --select S .` | Hardcoded secrets, eval(), shell=True, insecure patterns |
| Dep vulnerabilities | `pip-audit` | Known CVEs in installed packages |
| Secret detection | `git diff --cached \| grep ...` | Accidentally staged credentials |
| Config safety | `git status --ignored` | Sensitive files not in .gitignore |

## Common Mistakes

- Running `pip-audit` without the virtualenv active (scans system packages instead)
- Ignoring "moderate" severity findings — all levels must be addressed
- Skipping the scan "because it's just a small change" — all commits need scanning

## Red Flags

- **NEVER** commit with known vulnerabilities
- **NEVER** skip scanning for any reason
- **ALWAYS** scan dependencies, not just your own code
- **ALWAYS** verify `.gitignore` covers all sensitive files
