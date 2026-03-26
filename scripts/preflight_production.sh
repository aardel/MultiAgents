#!/usr/bin/env bash
set -euo pipefail

echo "Running production preflight checks..."

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not installed or not in PATH."
  exit 1
fi

if [ -z "${AGENT_ORCH_API_KEY:-}" ]; then
  echo "ERROR: AGENT_ORCH_API_KEY is required."
  exit 1
fi

if [ "${AGENT_ORCH_API_KEY}" = "dev-key" ]; then
  echo "WARNING: Using dev-key in production-like preflight."
fi

echo "Preflight checks passed."
