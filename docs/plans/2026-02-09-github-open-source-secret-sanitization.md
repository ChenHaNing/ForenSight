# GitHub Open-Source Secret Sanitization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove leaked credentials and sensitive artifacts from git history before open-sourcing the repository.

**Architecture:** Use two layers of protection: immediate credential rotation plus git history rewrite. History rewrite removes risky paths (`.env`, `.venv`) and replaces known leaked secret literals using `git filter-repo`. Then force-push sanitized history and run post-clean verification scans.

**Tech Stack:** git, git-filter-repo, ripgrep, bash

---

### Task 1: Baseline risk scan

**Files:**
- Read: `.env.example`
- Read: `.gitignore`
- Read: git history (`git log`, `git grep`)

1. Run a working tree secret regex scan.
2. Run full history scan for known key patterns.
3. Confirm sensitive files currently tracked/untracked.
4. Record leaked commit IDs and affected file paths.

### Task 2: Add repeatable tooling

**Files:**
- Create: `scripts/scan_secrets.sh`
- Create: `scripts/sanitize_git_history.sh`
- Create: `docs/security/open-source-safety-checklist.md`

1. Add a non-destructive scanner script for working tree + history.
2. Add a history sanitizer script that:
- backs up refs
- removes `.env` and `.venv` from all commits
- rewrites known leaked secret strings to placeholders
- prints exact force-push commands
3. Add a concise safety checklist for open-source publishing.

### Task 3: Verify tooling and output

**Files:**
- Test: `scripts/scan_secrets.sh`

1. Execute scanner script and confirm leaks are detected pre-sanitize.
2. Confirm scripts are executable and syntax-valid.
3. Validate documentation references real commands.

### Task 4: Execute history cleanup (user-approved step)

**Files:**
- Execute: `scripts/sanitize_git_history.sh`

1. Rotate all exposed keys at provider side.
2. Run sanitizer script in repo root.
3. Re-run scanner to confirm no leaked literals remain in history.
4. Force push rewritten history and request collaborators to re-clone.
