#!/usr/bin/env bash
set -euo pipefail

API_KEY="${AGENT_ORCH_API_KEY:-dev-key}"
BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "Starting production-like stack (backend + postgres)..."
docker compose up -d --build

echo "Waiting for backend health..."
for i in {1..30}; do
  if curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "Checking authenticated task creation..."
TASK_JSON="$(curl -fsS -X POST "${BASE_URL}/api/tasks" \
  -H "x-api-key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"project_label":"Prod Test","user_goal":"Run production validation"}')"
echo "${TASK_JSON}" | python3 -m json.tool

TASK_ID="$(echo "${TASK_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')"
echo "Task created: ${TASK_ID}"

echo "Fetching task by id..."
curl -fsS "${BASE_URL}/api/tasks/${TASK_ID}" -H "x-api-key: ${API_KEY}" | python3 -m json.tool

echo "Preparing PR draft..."
curl -fsS "${BASE_URL}/api/tasks/${TASK_ID}/prepare-pr" -H "x-api-key: ${API_KEY}" | python3 -m json.tool

echo "Production test passed."
