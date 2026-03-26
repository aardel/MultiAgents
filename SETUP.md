# Setup on Another PC (Cursor)

Use this guide to continue development on a new machine with minimal setup.

## 1) Prerequisites

- Cursor installed
- Git installed
- Python 3.11+ installed
- (Optional) Docker Desktop for production-like tests

## 2) Clone and open

```bash
git clone <YOUR_REPO_URL>
cd "AGENT ORCHESTRATION"
```

Open this folder in Cursor.

## 3) Configure environment

At repo root:

```bash
cp .env.example .env
```

Set at least:

- `AGENT_ORCH_ENV=development`
- `AGENT_ORCH_API_KEY=dev-key`

## 4) Bootstrap quickly

### macOS / Linux

```bash
chmod +x scripts/bootstrap_dev.sh
./scripts/bootstrap_dev.sh
```

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap_dev.ps1
```

## 5) Run the app

Backend:

```bash
cd backend
source .venv/bin/activate
export AGENT_ORCH_API_KEY=dev-key
uvicorn app.main:app --reload --port 8000
```

Frontend:

Open `frontend/index.html` in your browser.

## 6) Verify setup

From repo root:

```bash
export AGENT_ORCH_API_KEY=dev-key
./scripts/smoke_test.sh
```

Backend tests:

```bash
cd backend
source .venv/bin/activate
pytest -q
```
