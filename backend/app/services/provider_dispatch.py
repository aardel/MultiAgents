from __future__ import annotations

import os
import shutil
import subprocess

from app.models import DispatchTaskResponse, TaskState


PROVIDER_MAP = {
    "claude": {"cli": "claude", "api_env": "ANTHROPIC_API_KEY"},
    "codex": {"cli": "codex", "api_env": "OPENAI_API_KEY"},
    "gemini": {"cli": "gemini", "api_env": "GEMINI_API_KEY"},
    "openai": {"cli": "openai", "api_env": "OPENAI_API_KEY"},
    "copilot": {"cli": "gh", "api_env": "GITHUB_TOKEN"},
    "cursor": {"cli": "cursor-agent", "api_env": "CURSOR_API_KEY"},
}


def _run_cli_probe(cli: str) -> tuple[bool, str]:
    if shutil.which(cli) is None:
        return False, f"CLI '{cli}' is not installed."
    try:
        completed = subprocess.run(
            [cli, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
        return True, output or f"{cli} is available."
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"CLI probe failed: {exc}"


def dispatch_task_to_provider(
    task: TaskState,
    provider: str,
    mode: str = "auto",
) -> DispatchTaskResponse:
    key = provider.strip().lower()
    if key not in PROVIDER_MAP:
        raise ValueError(f"Unsupported provider: {provider}")
    spec = PROVIDER_MAP[key]

    cli = spec["cli"]
    api_env = spec["api_env"]
    has_api = bool(os.environ.get(api_env, "").strip())

    mode_used = mode
    output = ""
    if mode == "auto":
        ok, probe = _run_cli_probe(cli)
        if ok:
            mode_used = "cli"
            output = f"Dispatched via {provider} CLI. Probe output: {probe}"
        elif has_api:
            mode_used = "api"
            output = f"Dispatched via {provider} API credentials ({api_env})."
        else:
            mode_used = "not_configured"
            output = (
                f"Cannot dispatch to {provider}. Missing CLI and {api_env} is not configured."
            )
    elif mode == "cli":
        ok, probe = _run_cli_probe(cli)
        mode_used = "cli"
        output = (
            f"Dispatched via {provider} CLI. Probe output: {probe}"
            if ok
            else f"CLI dispatch failed: {probe}"
        )
    elif mode == "api":
        mode_used = "api"
        output = (
            f"Dispatched via {provider} API credentials ({api_env})."
            if has_api
            else f"API dispatch failed: missing env var {api_env}."
        )
    else:
        raise ValueError("mode must be one of: auto, cli, api")

    return DispatchTaskResponse(
        task_id=task.task_id,
        provider=provider,
        mode_used=mode_used,
        output=output,
    )
