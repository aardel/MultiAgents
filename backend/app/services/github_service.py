from __future__ import annotations

import json
import subprocess


def ensure_gh_available() -> bool:
    completed = subprocess.run(
        ["gh", "--version"],
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def push_branch(repo_path: str, branch_name: str) -> None:
    subprocess.run(
        ["git", "push", "-u", "origin", branch_name],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )


def create_pr(
    repo_path: str,
    title: str,
    body: str,
    head_branch: str,
    base_branch: str,
) -> str:
    completed = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--head",
            head_branch,
            "--base",
            base_branch,
        ],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return (completed.stdout or "").strip()


def get_pr_status(repo_path: str, pull_request_number: int) -> dict[str, object]:
    completed = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pull_request_number),
            "--json",
            "number,url,state,mergeable,isDraft",
        ],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads((completed.stdout or "{}").strip() or "{}")


def merge_pr(repo_path: str, pull_request_number: int, merge_method: str) -> None:
    method_flag = {
        "merge": "--merge",
        "squash": "--squash",
        "rebase": "--rebase",
    }.get(merge_method)
    if not method_flag:
        raise ValueError("merge_method must be one of: merge, squash, rebase")

    subprocess.run(
        ["gh", "pr", "merge", str(pull_request_number), method_flag, "--delete-branch"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
