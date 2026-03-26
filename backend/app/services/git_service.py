from __future__ import annotations

from pathlib import Path
import subprocess


def create_feature_branch(task_id: str) -> str:
    return f"ai/task-{task_id}"


def _run_git(repo_path: str, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return (completed.stdout or "").strip()


def ensure_git_repo(repo_path: str) -> bool:
    p = Path(repo_path)
    return (p / ".git").exists()


def checkout_task_branch(repo_path: str, branch_name: str) -> None:
    existing = _run_git(repo_path, ["branch", "--list", branch_name])
    if existing:
        _run_git(repo_path, ["checkout", branch_name])
        return
    _run_git(repo_path, ["checkout", "-b", branch_name])


def changed_files(repo_path: str) -> list[str]:
    out = _run_git(repo_path, ["diff", "--name-only"])
    if not out:
        return []
    return [line for line in out.splitlines() if line.strip()]


def diff_preview(repo_path: str, max_chars: int = 5000) -> str:
    out = _run_git(repo_path, ["diff"])
    if len(out) <= max_chars:
        return out
    return f"{out[:max_chars]}\n\n...diff truncated..."


def stage_all(repo_path: str) -> None:
    _run_git(repo_path, ["add", "."])


def has_staged_changes(repo_path: str) -> bool:
    out = _run_git(repo_path, ["diff", "--cached", "--name-only"])
    return bool(out.strip())


def commit_staged(repo_path: str, message: str) -> str:
    _run_git(repo_path, ["commit", "-m", message])
    return _run_git(repo_path, ["rev-parse", "--short", "HEAD"])
