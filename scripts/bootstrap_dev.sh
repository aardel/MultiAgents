#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[1/5] Ensuring .env exists..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "[2/5] Creating backend virtual environment..."
cd backend
python3 -m venv .venv

echo "[3/5] Installing backend dependencies..."
source .venv/bin/activate
pip install -r requirements.txt

echo "[4/5] Running backend tests..."
pytest -q

cd "${ROOT_DIR}"
echo "[5/5] Running smoke test..."
export AGENT_ORCH_API_KEY="${AGENT_ORCH_API_KEY:-dev-key}"
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh || true

echo ""
echo "Bootstrap complete."
echo "Start backend with:"
echo "  cd backend && source .venv/bin/activate && export AGENT_ORCH_API_KEY=dev-key && uvicorn app.main:app --reload --port 8000"
