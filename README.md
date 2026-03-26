# Agent Orchestration MVP

Beginner-first starter project for orchestrating multiple AI coding agents behind a single manager workflow.

## Project objectives

- Provide a practical reference implementation for managing multi-agent coding workflows through one control plane.
- Reduce manual orchestration overhead by turning a plain-English goal into an executable, auditable task lifecycle.
- Keep operations safe and production-minded with API keys, request tracing, rate limiting, and structured logs.
- Support both local and SSH-connected repositories so teams can adopt incrementally without major infrastructure changes.
- Produce review-ready development output (branch changes, test signals, commit flow, and PR draft support) for human approval.

### Success criteria

- A new user can run the stack locally in minutes and create a task end-to-end.
- Each task has visible state transitions, event history, and reproducible outputs.
- Generated code changes stay isolated to task branches and can be reviewed before merge.
- CI validates core backend behavior on every push and pull request.

## What this includes

- FastAPI backend for:
  - local or SSH project connection preflight
  - task creation and manager-run simulation
  - real local task execution on a git branch
  - SQLite or Postgres persistence for tasks and project connection state
  - task status polling
- Simple frontend (HTML/CSS/JS) for:
  - entering project details
  - submitting a task in plain language
  - viewing progress and review-ready output

## Structure

- `backend/` API and orchestration logic
- `frontend/` static UI

## Quick start

For moving this project to another PC, see `SETUP.md`.

### 1) Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export AGENT_ORCH_API_KEY=dev-key
uvicorn app.main:app --reload --port 8000
```

### 2) Frontend

Open `frontend/index.html` in your browser.

By default it calls `http://localhost:8000`.
By default frontend uses API key `dev-key` (for local development).

### 3) Smoke test

```bash
chmod +x scripts/smoke_test.sh
export AGENT_ORCH_API_KEY=dev-key
./scripts/smoke_test.sh
```

### 4) Backend tests

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

### 5) Bootstrap scripts

macOS/Linux:

```bash
chmod +x scripts/bootstrap_dev.sh
./scripts/bootstrap_dev.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_dev.ps1
```

## Docker Deploy (production-like)

Run backend + Postgres:

```bash
export AGENT_ORCH_API_KEY=dev-key
docker compose up --build
```

Backend will be available at `http://localhost:8000`.

## Security (current)

- All `/api/*` endpoints require `x-api-key` header.
- Primary key is `AGENT_ORCH_API_KEY` (defaults to `dev-key` in development).
- Optional rotation key `AGENT_ORCH_PREVIOUS_API_KEY` is also accepted during migration.
- CORS origins come from `AGENT_ORCH_ALLOWED_ORIGINS` in non-development modes.
- API rate limiting is enabled per client IP with `AGENT_ORCH_RATE_LIMIT_PER_MIN`.
- Every response includes `x-request-id` for easier troubleshooting.
- Backend writes structured JSON log events for request completion and failures.
- Task lifecycle actions are stored in DB audit events (`/api/tasks/{task_id}/events`).
- Provider readiness can be checked via `/api/providers` (CLI/API-key availability snapshot).
- Tasks can be dispatched through provider adapters via `/api/tasks/{task_id}/dispatch`.
- SSH-connected tasks can run remote commands via `/api/tasks/{task_id}/execute-ssh`.
- GitHub PR status/merge automation is available via `/api/github/pr-status` and `/api/github/merge-pr`.
- Long-running work can run asynchronously via `/api/tasks/{task_id}/jobs` and `/api/jobs/{job_id}`.
- `GET /health` remains open for infra health checks.

## Production Test

Run an end-to-end production-like validation:

```bash
chmod +x scripts/preflight_production.sh
chmod +x scripts/production_test.sh
export AGENT_ORCH_API_KEY=dev-key
./scripts/preflight_production.sh
./scripts/production_test.sh
```

This starts Docker services, checks health, creates/fetches a task, and validates PR draft generation against Postgres.

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` runs backend tests on pushes and pull requests.

## MVP Flow

1. Connect project (local path or SSH host/path)
2. Enter goal (for example: "Add login page with tests")
3. Manager creates a plain-English plan
4. Click "Execute Local" to:
   - switch to task branch
   - write a task note file for audit trail
   - run auto-detected tests when available
   - return changed files and git diff preview
5. Click "Commit Changes" to create a local commit on task branch
6. Click "Prepare PR Draft" to generate title/body for GitHub PR
7. Click "Create GitHub PR" for one-click push + PR creation (requires `gh auth login`)
8. Or click "Run All" to execute local, commit, and open PR in one step
9. Or click "Run Async" to queue a background pipeline and monitor job status
10. Follow the timeline chips to see current stage and failures clearly
11. Read the plain-English status message for what to do next
12. If tests fail, click "Fix It For Me" to auto-create a recovery task
13. Use advanced controls to check providers, dispatch tasks, run SSH command, and view task events

## Next steps

### Done

- GitHub PR creation and CI checks are implemented.
- Background async job orchestration with polling is implemented.
- Provider readiness and dispatch endpoints are implemented.

### In progress

- Provider adapters for each AI CLI (baseline support exists; broaden and harden provider-specific behavior).
- Backend test coverage expansion (tests exist; continue broadening edge-case and integration coverage).

### Planned

- Real git worktree execution for stronger task isolation.
- Richer authentication and role-based access control.

See `PROJECT_OBJECTIVES.md` for a concise problem statement, scope boundaries, and phased roadmap.
