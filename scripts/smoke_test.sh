#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
API_KEY="${AGENT_ORCH_API_KEY:-dev-key}"

echo "Checking health..."
curl -sS "${BASE_URL}/health" | python3 -m json.tool

echo "Creating task..."
TASK_JSON="$(curl -sS -X POST "${BASE_URL}/api/tasks" \
  -H "x-api-key: ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"project_label":"Smoke Test","user_goal":"Create demo change"}')"
echo "${TASK_JSON}" | python3 -m json.tool

TASK_ID="$(echo "${TASK_JSON}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["task_id"])')"
echo "Task ID: ${TASK_ID}"

echo "Preparing PR draft..."
curl -sS "${BASE_URL}/api/tasks/${TASK_ID}/prepare-pr" \
  -H "x-api-key: ${API_KEY}" | python3 -m json.tool

echo "Smoke test completed."
