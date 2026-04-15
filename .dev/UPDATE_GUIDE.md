# Update Guide — Keeping AGENTS.md and .dev/ in Sync

This document describes the workflow for updating project documentation when code changes.

## When to Update

Update documentation when any of these occur:
- New module/file added or existing one renamed/deleted
- API endpoint added, changed, or removed
- New configuration keys introduced
- Function signatures change in public APIs
- New design patterns or conventions established
- Error handling or logging patterns change

## Update Workflow

### Step 1: Run diff summary

```bash
bash .dev/scripts/diff-summary.sh
```

This shows what changed since the last documentation sync. On first run, it compares against the initial commit.

### Step 2: Analyze changes

Review the diff summary output. Focus on:
- New/deleted source files → update module map in `AGENTS.md`
- Changed API routes → update `.dev/api-reference.md`
- New functions → update `.dev/function-index.md`
- Config changes → update `.dev/config-reference.md`
- Architecture changes → update `.dev/architecture.md`

### Step 3: Update relevant files

**Important**: First, list all `.dev/*.md` files to discover the current set. Do NOT rely on a hardcoded list — new files may have been added.

```bash
ls .dev/*.md
```

Then update each affected file.

### Step 4: Decide if a new .dev/ file is needed

Create a new `.dev/<topic>.md` file when ALL of these are true:
1. The topic doesn't fit naturally into any existing `.dev/` file
2. It's too detailed for `AGENTS.md` (which should stay under 150 lines)
3. Developers would need this reference when working on related features

When creating a new file:
- Add it to the "Deep References" table in `AGENTS.md`
- Add it to the "File Inventory" table below
- Keep it under 300 lines; split into focused sub-files if larger

### Step 5: Mark sync point

```bash
bash .dev/scripts/diff-summary.sh --mark
```

This saves the current HEAD as the baseline for future diffs.

### Step 6: Report to user

Summarize what was updated and why.

## File Inventory

| File | Purpose | Update triggers |
|---|---|---|
| `AGENTS.md` | Root guide — module map, naming rules, quick reference | New modules, renamed files, convention changes |
| `.dev/architecture.md` | System design, concurrency, data structures, pitfalls | Architectural changes, new services, threading changes |
| `.dev/api-reference.md` | Full API listing, request/response formats | New/changed endpoints, auth changes |
| `.dev/coding-style.md` | Naming examples, error patterns, test guide | Convention changes, new patterns adopted |
| `.dev/function-index.md` | Function lookup by developer intent | New public functions, signature changes |
| `.dev/config-reference.md` | All config keys, types, defaults | New env vars, default changes, Docker config |
| `.dev/UPDATE_GUIDE.md` | This file — self-maintaining workflow | New .dev/ files added or removed |
| `.dev/scripts/diff-summary.sh` | Diff summary helper script | Rarely (script logic changes only) |

## Sync Point File

The file `.skill-sync-commit` in the project root stores the last synced commit hash. It is:
- Created by `diff-summary.sh --mark`
- Listed in `.gitignore` (local-only, not committed)
- Used as the baseline for `diff-summary.sh` to detect changes

## Guidelines for Each File

### AGENTS.md (< 150 lines)
- Keep compact — one-liner descriptions only
- Module map: flat table, no nesting
- Link to `.dev/` files for details

### .dev/ files (< 300 lines each)
- Written for AI tools that need deeper context
- Include real code examples extracted from the codebase
- Organize by developer intent, not by file structure
- Keep cross-references between files when relevant
