# Tool Access — AI Agent Policy

Scope of what AI agents operating inside this repository are authorized to do.
"When in doubt, ask the human" is the catch-all rule.

## 1. Available Capabilities

Agents SHOULD use these freely to complete routine tasks:

- **Read and write source files** inside `backend/`, `frontend-react/src/`, `tests/`, `.dev/`, and root documentation (`README.md`, `AGENTS.md`, `CLAUDE.md`, `PROGRESS.md`). Match the surrounding style.
- **Execute shell commands** for verification, dependency installs, and builds as documented in `AGENTS.md`. Prefer running from the repo root; resolve it via `git rev-parse --show-toplevel` in scripts.
- **Git operations**: `status`, `diff`, `log`, `add`, `commit`, `checkout -b <branch>`, `branch`, `merge --no-ff` into feature branches, `pull`, `push` to the current feature branch after verification.
- **Create exec-plans and update PROGRESS.md** to preserve multi-session context.
- **Create temporary files** only inside `temp/`, `outputs/`, or `uploads/` (already gitignored runtime dirs).

## 2. Common Command Reference

### Dependency management
| Goal | Command |
|---|---|
| Install backend deps | `python -m pip install -r backend/requirements.txt` |
| Install dev deps | `python -m pip install -r requirements-dev.txt` |
| Add a Python dep | Edit `backend/requirements.txt`, then `python -m pip install -r backend/requirements.txt` |
| Install frontend deps | `npm --prefix frontend-react install` |
| Add a frontend dep | `npm --prefix frontend-react install <pkg>` (commits the `package.json` + `package-lock.json` diff) |
| Audit outdated deps | `npm --prefix frontend-react outdated` / `python -m pip list --outdated` |

### Testing
| Goal | Command |
|---|---|
| Full backend test suite | `python -m pytest tests/ -q` |
| Single test file | `python -m pytest tests/test_<module>.py -q` |
| Single test function | `python -m pytest tests/test_<module>.py::test_<name> -q` |
| Collect only | `python -m pytest tests/ --collect-only -q` |
| No frontend unit tests are configured | — (verify via ESLint + `tsc` build) |

### Code quality
| Goal | Command |
|---|---|
| Backend lint (CI scope) | `python -m flake8 tests backend/shared backend/services backend/models.py backend/task_persistence.py` |
| Frontend lint | `npm --prefix frontend-react run lint` |
| Frontend type check + build | `npm --prefix frontend-react run build` |
| Full check | `bash .dev/scripts/verify.sh` |

### Build / run
| Goal | Command |
|---|---|
| Backend dev server | `python -m uvicorn backend.app:app --host 0.0.0.0 --port 5000 --reload` |
| Frontend dev server | `npm --prefix frontend-react run dev` |
| Frontend production bundle | `npm --prefix frontend-react run build` |
| Docker compose up | `docker compose up --build` |

### Database
| Goal | Command |
|---|---|
| Apply schema + incremental migrations | auto-runs on app startup via `backend.database.init_db` |
| Inspect dev SQLite | `python -c "import sqlite3; print(sqlite3.connect('tasks.db').execute('select count(*) from tasks').fetchone())"` |
| Back up dev DB | `cp tasks.db tasks.db.bak` (outside of git tracking) |
| Write a new migration | Extend `_run_migrations()` in `backend/database.py` with an `ALTER TABLE` guarded by an `inspect()` check |

### Git
| Goal | Command |
|---|---|
| Current state | `git status` |
| Scoped diff | `git diff -- backend/ frontend-react/ tests/` |
| Staged diff before commit | `git diff --cached` |
| Commit | `git commit -m "<type>: <imperative summary>"` |
| Branch off | `git checkout -b <feature-branch>` |
| Push feature branch | `git push -u origin <feature-branch>` |
| Summarize current scope | `bash .dev/scripts/diff-summary.sh` |

## 3. Forbidden Operations (Safety Rails)

Agents MUST NOT:

- **NEVER modify `.env`, any file containing `HF_TOKEN` / `api_key` / `PASSWORD`, or docker-compose secrets.** If a secret value needs to change, ask the human.
- **NEVER commit secrets to git.** Run `git diff --cached` before every commit and abort if it contains tokens, API keys, or passwords.
- **NEVER execute destructive database operations** (`DROP TABLE`, `TRUNCATE`, `DELETE FROM ... WHERE 1=1`, `rm tasks.db`). For schema changes, write a guarded migration in `backend/database.py:_run_migrations`.
- **NEVER delete files under `outputs/`, `uploads/`, `temp/`, or the `faster-whisper-large-v3-zh-TW/` model directory** — they contain user artifacts or large downloads.
- **NEVER run `git push --force`, `git push --force-with-lease`, or `git reset --hard` on `main` or `master`.** Use a fresh feature branch instead.
- **NEVER install a dependency without updating the manifest** (`backend/requirements.txt` or `frontend-react/package.json` + its lockfile).
- **NEVER commit binaries, `node_modules/`, `.venv/`, `*.db`, `*.log`, `outputs/`, or `uploads/`.** These are already listed in `.gitignore`; do not add overrides.
- **NEVER weaken security posture**: no `allow_origins=["*"]` tightening to something broader, no disabling of TLS verification, no hardcoded credentials, no adding `# noqa` just to silence flake8.
- **NEVER modify `.github/workflows/*`, `.flake8`, `Dockerfile`, `docker-compose.yml`, or `pyproject.toml` without explicit user approval.**
- **NEVER bypass the required verification step** in `AGENTS.md` Section 1 before reporting a task complete.

## 4. Escalation Rules — Stop and Ask When…

Frame these as "ask before acting", not "give up":

- **Architectural change** — a refactor that touches ≥2 of `backend/app.py`, `backend/services/`, `backend/shared/`, or introduces a new global state container.
- **Schema change** — modifying `TaskRecord`, `FolderRecord`, or adding a new SQLAlchemy model. Requires a migration plan and user approval.
- **Security-sensitive change** — auth, CORS policy, file-upload validation, subprocess invocation, any use of user-controlled paths in `os.path.join`.
- **Dependency upgrade with breaking changes** — major-version bumps of FastAPI, Pydantic, SQLAlchemy, React, Vite, or any torch/cuda revision.
- **Changes affecting production data** — anything that rewrites existing rows in `tasks` or `folders`, or touches `outputs/`.
- **New external service integration** — new LLM endpoint, cloud storage, webhook destination.
- **Unfamiliar pattern** — the surrounding code does it one way; you believe a different way is better. Prefer matching the existing pattern; escalate if the difference is important.
- **Unclear requirement** — specification is ambiguous or contradicts existing code.

The final rule always applies: **when in doubt, ask the human.**
