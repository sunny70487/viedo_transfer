# Instruction Layer — Update Guide

This is the self-maintaining workflow for the agent instruction files. The goal is: whenever the codebase changes shape, these files are refreshed in the same PR.

## File Inventory

| File | Owner domain | Refresh trigger |
|---|---|---|
| `AGENTS.md` | Root instruction — read first by agents | Any change to verification commands, architectural rules, or module map |
| `CLAUDE.md` | Exact duplicate of `AGENTS.md` for Claude-specific tools | Keep byte-equal to `AGENTS.md` |
| `.dev/architecture.md` | System design, concurrency, globals, pitfalls | New module relationships, thread changes, new globals |
| `.dev/api-reference.md` | Endpoint listing + add-endpoint recipe | Any route added / renamed / removed |
| `.dev/coding-style.md` | Naming, error handling, logging, templates | New convention introduced, template needs updating |
| `.dev/function-index.md` | Intent-based lookup table | New public helper added, existing helper moved/renamed |
| `.dev/config-reference.md` | Env vars, constants, schema | New env var, DB column, module constant |
| `.dev/UPDATE_GUIDE.md` | This file | When the update workflow itself changes |
| `.dev/scripts/diff-summary.sh` | Git-based diff helper | When summary fields need adjusting |
| `.dev/scripts/verify.sh` | Single entry-point for lint + tests + frontend build | When verification steps change (keep in sync with `AGENTS.md`) |
| `.dev/exec-plans/templates/exec-plan-template.md` | Multi-step plan skeleton | When plan section conventions change |
| `.dev/exec-plans/active/` | In-progress plans (committed) | Add/remove one file per plan; move to `completed/` when done |
| `.dev/exec-plans/completed/` | Finished plans kept for decision history | Never delete — append new completed plans here |
| `PROGRESS.md` (root, gitignored) | Local per-session state tracker | Update at end of each session; read at start of each session |
| `.dev/tool-access.md` | AI agent capability + forbidden-ops policy | When adding/removing common commands, changing forbidden ops, or escalation rules |

## When to Update

Trigger | Files to touch
---|---
Added/removed/renamed an endpoint | `.dev/api-reference.md`, `AGENTS.md` (if a module appeared/disappeared), `CLAUDE.md`
Added a new Python module under `backend/services/` or `backend/shared/` | `AGENTS.md` module map, `CLAUDE.md`, `.dev/function-index.md`, `.dev/architecture.md` if it holds state
Added/removed a global or changed an injector | `.dev/architecture.md` ("Key Globals"), `AGENTS.md` hard constraints
Added an env var | `.dev/config-reference.md`
Changed a Pydantic / ORM model | `.dev/config-reference.md` (if DB schema), `.dev/api-reference.md` (if request/response)
Renamed / moved an existing helper | `.dev/function-index.md`, grep for any other references
Updated verification commands or CI | `AGENTS.md`, `CLAUDE.md`, `.dev/coding-style.md` checklist, `.dev/config-reference.md`
Introduced a new naming or error convention | `.dev/coding-style.md`, and add a table row to `AGENTS.md` + `CLAUDE.md`

## Workflow

1. Before starting a refactor, run `.dev/scripts/diff-summary.sh` to get the current scope.
2. Make the code change.
3. Run the full verification: `bash .dev/scripts/verify.sh` (or `--backend-only` / `--frontend-only` to narrow scope). Success ends with `--- verify.sh OK ---`.
4. Re-run `.dev/scripts/diff-summary.sh` and review which doc files the trigger table says to touch.
5. Update `AGENTS.md` + `CLAUDE.md` first (they are kept in sync — copy one to the other). Use a plain file copy; do not hand-maintain two drifting versions.
6. Update any `.dev/*.md` files listed for your trigger.
7. Stage every modified instruction file in the same commit as the code change:
   ```
   git add AGENTS.md CLAUDE.md .dev/
   ```

## Keep AGENTS.md and CLAUDE.md in Sync

On POSIX, a symlink is acceptable:
```
ln -sf AGENTS.md CLAUDE.md
```
On Windows or when symlinks are not supported, maintain them as byte-equal copies. The test is:
```
git diff --no-index AGENTS.md CLAUDE.md
```
which must produce no output.

## Validation Tips

- Every path mentioned should be relative to the repo root (use `git rev-parse --show-toplevel` to confirm when scripting).
- Every command in a fenced block must be copy-pasteable and executable from the repo root on a fresh shell.
- When citing a real line of code, include the file path; do not include the absolute filesystem path.
- If you're uncertain what changed, run `git diff main... -- backend/ frontend-react/ tests/` and let the diff drive the doc update.

## Review Checklist for Reviewers

Before approving a PR:

- [ ] Does the PR change any public function in `backend/services/` or `backend/shared/`? If yes, is `.dev/function-index.md` updated?
- [ ] Does the PR add/remove a route? If yes, is `.dev/api-reference.md` updated?
- [ ] Does the PR add an env var? If yes, is `.dev/config-reference.md` updated?
- [ ] Are `AGENTS.md` and `CLAUDE.md` still identical?
- [ ] Do the verification commands in `AGENTS.md` still match `.github/workflows/ci.yml`?
