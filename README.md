# Agent Orchestration MVP

Beginner-first starter project for orchestrating multiple AI coding agents behind a single manager workflow.

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
9. Follow the timeline chips to see current stage and failures clearly
10. Read the plain-English status message for what to do next
11. If tests fail, click "Fix It For Me" to auto-create a recovery task

## Next steps

- Add real git worktree execution
- Add provider adapters for each AI CLI
- Add GitHub PR creation and CI checks
- Add richer auth and role-based access
- Expand backend test coverage
