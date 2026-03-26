from __future__ import annotations

import os
import shutil
import subprocess
import shlex

from app.models import DispatchTaskResponse, TaskState


PROVIDER_MAP = {
    "claude": {"cli": "claude", "api_env": "ANTHROPIC_API_KEY"},
    "codex": {"cli": "codex", "api_env": "OPENAI_API_KEY"},
    "gemini": {"cli": "gemini", "api_env": "GEMINI_API_KEY"},
    "openai": {"cli": "openai", "api_env": "OPENAI_API_KEY"},
    "copilot": {"cli": "gh", "api_env": "GITHUB_TOKEN"},
    "cursor": {"cli": "cursor-agent", "api_env": "CURSOR_API_KEY"},
}

PROVIDER_CAPABILITIES = {
    "claude": "frontend UX, product copy, refactors",
    "codex": "code implementation, repo edits, CLI-heavy tasks",
    "gemini": "tests, analysis, documentation polish",
    "openai": "general implementation and reasoning",
    "copilot": "code suggestions and fast scaffolding",
    "cursor": "editor-driven implementation workflows",
}

CLI_EXEC_CANDIDATES = {
    "codex": [
        ["codex", "exec", "--sandbox", "workspace-write", "{prompt}"],
        ["codex", "exec", "--sandbox", "workspace-write", "-p", "{prompt}"],
    ],
    "claude": [
        [
            "claude",
            "--permission-mode",
            "acceptEdits",
            "-p",
            "{prompt}",
        ],
        ["claude", "--permission-mode", "bypassPermissions", "-p", "{prompt}"],
    ],
    "gemini": [
        ["gemini", "--approval-mode", "auto_edit", "-p", "{prompt}"],
        ["gemini", "-p", "{prompt}"],
    ],
    "openai": [["openai", "api", "responses.create", "--input", "{prompt}"]],
    "copilot": [["gh", "copilot", "suggest", "{prompt}"]],
    "cursor": [["cursor-agent", "-p", "{prompt}"], ["cursor-agent", "{prompt}"]],
}


def _run_cli_probe(cli: str) -> tuple[bool, str, str]:
    if shutil.which(cli) is None:
        return False, f"{cli} --version", f"CLI '{cli}' is not installed."
    try:
        command = f"{cli} --version"
        completed = subprocess.run(
            [cli, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
        return True, command, output or f"{cli} is available."
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"{cli} --version", f"CLI probe failed: {exc}"


def _build_provider_prompt(task: TaskState, provider: str) -> str:
    capability = PROVIDER_CAPABILITIES.get(provider, "general coding tasks")
    return (
        f"You are provider '{provider}' focused on {capability}. "
        f"Work on this repository task: {task.user_goal}. "
        "Make concrete code changes in the current repository, "
        "prefer small safe commits, and include tests where reasonable."
    )


def _attempt_cli_execution(
    provider: str,
    prompt: str,
    repo_path: str,
    flow: list[str],
) -> tuple[bool, str]:
    candidates = CLI_EXEC_CANDIDATES.get(provider, [])
    if not candidates:
        flow.append("no_cli_exec_templates")
        return False, ""

    # Codex generally needs more time; Claude may be slower to initialize.
    # Keep Gemini tighter to avoid long stalls.
    per_provider_timeout = {
        "codex": 120,
        "claude": 90,
        "gemini": 60,
        "openai": 60,
        "copilot": 45,
        "cursor": 60,
    }.get(provider, 60)

    for template in candidates:
        args = [part.replace("{prompt}", prompt) for part in template]
        flow.append("try_exec: " + shlex.join(args))
        try:
            completed = subprocess.run(
                args,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=per_provider_timeout,
            )
            output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
            flow.append(f"exec_exit_code={completed.returncode}")
            if completed.returncode == 0:
                return True, output
        except Exception as exc:  # pragma: no cover - defensive
            flow.append(f"exec_error={exc}")
            continue
    return False, ""


def _format_provider_exec_output(exec_output: str, max_chars: int = 20000) -> str:
    """
    Keep provider CLI output readable by returning head + tail when oversized.
    This mimics the "terminal transcript" feel without dumping arbitrarily huge logs.
    """
    text = (exec_output or "").strip()
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.55)]
    tail = text[-int(max_chars * 0.45) :]
    return head + "\n\n... [output truncated] ...\n\n" + tail


def dispatch_task_to_provider(
    task: TaskState,
    provider: str,
    mode: str = "auto",
    repo_path: str | None = None,
) -> DispatchTaskResponse:
    key = provider.strip().lower()
    if key not in PROVIDER_MAP:
        raise ValueError(f"Unsupported provider: {provider}")
    spec = PROVIDER_MAP[key]

    cli = spec["cli"]
    api_env = spec["api_env"]
    has_api = bool(os.environ.get(api_env, "").strip())
    flow: list[str] = [f"provider={key}", f"requested_mode={mode}", f"cli={cli}", f"api_env={api_env}"]
    # Prefer CLI authentication/workflows. If the provider CLI is available and
    # we have a repo path, we attempt the non-interactive workload execution
    # regardless of whether a matching API env var is set.
    allow_execution = repo_path is not None and key in CLI_EXEC_CANDIDATES

    mode_used = mode
    output = ""
    prompt_sent = _build_provider_prompt(task, key)
    executed = False
    if mode == "auto":
        ok, command, probe = _run_cli_probe(cli)
        flow.append(f"run: {command}")
        flow.append(f"cli_probe_ok={ok}")
        if ok:
            mode_used = "cli"
            output = f"Dispatched via {provider} CLI. Probe output: {probe}"
            flow.append("mode_selected=cli")
            if repo_path:
                ran, exec_output = _attempt_cli_execution(key, prompt_sent, repo_path, flow) if allow_execution else (False, "")
                executed = ran
                if ran:
                    excerpt = _format_provider_exec_output(exec_output)
                    output = (
                        f"Executed via {provider} CLI with workload prompt. "
                        f"Output excerpt: {excerpt}"
                    )
        elif has_api:
            mode_used = "api"
            output = f"Dispatched via {provider} API credentials ({api_env})."
            flow.append("mode_selected=api")
        else:
            mode_used = "not_configured"
            output = (
                f"Cannot dispatch to {provider}. Missing CLI and {api_env} is not configured."
            )
            flow.append("mode_selected=not_configured")
    elif mode == "cli":
        ok, command, probe = _run_cli_probe(cli)
        flow.append(f"run: {command}")
        flow.append(f"cli_probe_ok={ok}")
        mode_used = "cli"
        output = (
            f"Dispatched via {provider} CLI. Probe output: {probe}"
            if ok
            else f"CLI dispatch failed: {probe}"
        )
        flow.append("mode_selected=cli")
        if ok and repo_path:
            ran, exec_output = _attempt_cli_execution(key, prompt_sent, repo_path, flow) if allow_execution else (False, "")
            executed = ran
            if ran:
                excerpt = _format_provider_exec_output(exec_output)
                output = (
                    f"Executed via {provider} CLI with workload prompt. "
                    f"Output excerpt: {excerpt}"
                )
    elif mode == "api":
        mode_used = "api"
        flow.append(f"api_key_present={has_api}")
        output = (
            f"Dispatched via {provider} API credentials ({api_env})."
            if has_api
            else f"API dispatch failed: missing env var {api_env}."
        )
        flow.append("mode_selected=api")
    else:
        raise ValueError("mode must be one of: auto, cli, api")

    return DispatchTaskResponse(
        task_id=task.task_id,
        provider=provider,
        mode_used=mode_used,
        output=output,
        command_flow=flow,
        executed=executed,
        prompt_sent=prompt_sent,
    )
