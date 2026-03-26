from __future__ import annotations

from uuid import uuid4
from contextlib import asynccontextmanager
from typing import Optional
import logging
import time
import os
import json
import queue
import threading
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from starlette.responses import JSONResponse

from app.models import (
    ConnectProjectRequest,
    ConnectProjectResponse,
    CreatePrRequest,
    CreatePrResponse,
    PreparePrResponse,
    RunAllRequest,
    RunAllResponse,
    TaskRequest,
    TaskEvent,
    ProvidersResponse,
    DispatchTaskRequest,
    DispatchTaskResponse,
    DispatchManyTaskRequest,
    DispatchManyTaskResponse,
    ExecuteSshRequest,
    ExecuteSshResponse,
    PullRequestStatusRequest,
    PullRequestStatusResponse,
    MergePullRequestRequest,
    MergePullRequestResponse,
    EnqueueJobRequest,
    EnqueueJobResponse,
    ExecuteSshRequest,
    TaskState,
    TaskJob,
    JobStatus,
    TaskStatus,
)
from app.config import allowed_origins, api_key, previous_api_key, validate_runtime_config
from app.services.execution import (
    detect_test_command,
    run_shell,
    write_task_note,
)
from app.services.git_service import (
    changed_files,
    checkout_task_branch,
    commit_staged,
    create_feature_branch,
    diff_preview,
    ensure_git_repo,
    has_staged_changes,
    stage_all,
)
from app.services.github_service import (
    create_pr,
    ensure_gh_available,
    get_pr_status,
    merge_pr,
    push_branch,
)
from app.services.manager import advance_task, build_plan
from app.services.persistence import (
    add_task_event,
    get_value,
    init_db,
    load_task_job,
    list_task_events,
    load_task,
    save_task,
    save_task_job,
    set_value,
)
from app.services.preflight import run_preflight
from app.services.provider_dispatch import dispatch_task_to_provider
from app.services.providers import get_provider_statuses
from app.services.ssh_service import get_ssh_target, run_remote_command

logger = logging.getLogger("agent_orch")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

RATE_LIMIT_PER_MIN = int(os.environ.get("AGENT_ORCH_RATE_LIMIT_PER_MIN", "120"))
_RATE_BUCKETS: dict[str, list[float]] = {}
JOB_QUEUE: "queue.Queue[str]" = queue.Queue()
WORKER_STARTED = False


def _log_json(event: str, **fields: object) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, default=str))


def reset_rate_limit_state() -> None:
    _RATE_BUCKETS.clear()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_rate_limited(client_key: str) -> tuple[bool, int]:
    if RATE_LIMIT_PER_MIN <= 0:
        return False, 0
    now = time.time()
    window_start = now - 60
    bucket = [ts for ts in _RATE_BUCKETS.get(client_key, []) if ts >= window_start]
    if len(bucket) >= RATE_LIMIT_PER_MIN:
        retry_after = max(1, int(60 - (now - bucket[0])))
        _RATE_BUCKETS[client_key] = bucket
        return True, retry_after
    bucket.append(now)
    _RATE_BUCKETS[client_key] = bucket
    return False, 0

def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    accepted = {api_key()}
    old = previous_api_key()
    if old:
        accepted.add(old)
    if x_api_key not in accepted:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@asynccontextmanager
async def lifespan(_: FastAPI):
    global WORKER_STARTED
    validate_runtime_config()
    init_db()
    if not WORKER_STARTED:
        t = threading.Thread(target=_worker_loop, daemon=True, name="job-worker")
        t.start()
        WORKER_STARTED = True
    yield


app = FastAPI(title="Agent Orchestration MVP", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_and_rate_limit(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid4().hex[:12])
    client_host = request.client.host if request.client else "unknown"
    start = time.time()

    if request.url.path.startswith("/api/"):
        limited, retry_after = _is_rate_limited(client_host)
        if limited:
            _log_json(
                "rate_limited",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                client_ip=client_host,
                retry_after=retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Slow down and retry shortly.",
                    "request_id": request_id,
                },
                headers={"x-request-id": request_id, "retry-after": str(retry_after)},
            )

    try:
        response = await call_next(request)
    except Exception:
        _log_json(
            "unhandled_error",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=client_host,
        )
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "request_id": request_id},
        )

    duration_ms = int((time.time() - start) * 1000)
    _log_json(
        "request_complete",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
        client_ip=client_host,
    )
    response.headers["x-request-id"] = request_id
    return response

def _get_task_or_404(task_id: str) -> TaskState:
    task = load_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _get_job_or_404(job_id: str) -> TaskJob:
    job = load_task_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _get_connected_local_path_or_400() -> str:
    mode = get_value("connected_mode")
    path = get_value("connected_path")
    if mode != "local" or not path:
        raise HTTPException(status_code=400, detail="No local project connected")
    return path


def _get_connected_ssh_or_400() -> tuple[str, str, str]:
    mode = get_value("connected_mode")
    user = get_value("connected_ssh_user")
    host = get_value("connected_ssh_host")
    path = get_value("connected_ssh_path")
    if mode != "ssh" or not user or not host or not path:
        raise HTTPException(status_code=400, detail="No SSH project connected")
    return user, host, path


def _process_job(job_id: str) -> None:
    job = load_task_job(job_id)
    if not job:
        return
    job.status = JobStatus.RUNNING
    job.updated_at = _utc_now()
    save_task_job(job)
    add_task_event(job.task_id, "job_running", f"Job {job.job_id} started ({job.job_type}).")
    try:
        if job.job_type == "run_all":
            resp = run_all(job.task_id, RunAllRequest(**job.params))
            job.result = resp.model_dump(mode="json")
        elif job.job_type == "execute_local":
            resp = execute_task_local(job.task_id)
            job.result = resp.model_dump(mode="json")
        elif job.job_type == "execute_ssh":
            resp = execute_task_ssh(job.task_id, ExecuteSshRequest(**job.params))
            job.result = resp.model_dump(mode="json")
        elif job.job_type == "dispatch":
            resp = dispatch_task(job.task_id, DispatchTaskRequest(**job.params))
            job.result = resp.model_dump(mode="json")
        else:
            raise ValueError(f"Unsupported job_type: {job.job_type}")
        job.status = JobStatus.SUCCEEDED
        add_task_event(job.task_id, "job_succeeded", f"Job {job.job_id} completed.")
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        add_task_event(job.task_id, "job_failed", f"Job {job.job_id} failed: {exc}")
    finally:
        job.updated_at = _utc_now()
        save_task_job(job)


def _worker_loop() -> None:
    while True:
        job_id = JOB_QUEUE.get()
        try:
            _process_job(job_id)
        finally:
            JOB_QUEUE.task_done()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/providers", response_model=ProvidersResponse)
def providers_status(_: None = Depends(require_api_key)) -> ProvidersResponse:
    return ProvidersResponse(providers=get_provider_statuses())


@app.post("/api/github/pr-status", response_model=PullRequestStatusResponse)
def github_pr_status(
    payload: PullRequestStatusRequest,
    _: None = Depends(require_api_key),
) -> PullRequestStatusResponse:
    repo_path = _get_connected_local_path_or_400()
    if not ensure_gh_available():
        raise HTTPException(status_code=400, detail="GitHub CLI (gh) is not available.")
    try:
        status = get_pr_status(repo_path, payload.pull_request_number)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to fetch PR status: {exc}") from exc

    return PullRequestStatusResponse(
        pull_request_number=int(status.get("number", payload.pull_request_number)),
        url=str(status.get("url", "")),
        state=str(status.get("state", "UNKNOWN")),
        mergeable=str(status.get("mergeable", "UNKNOWN")),
        is_draft=bool(status.get("isDraft", False)),
    )


@app.post("/api/github/merge-pr", response_model=MergePullRequestResponse)
def github_merge_pr(
    payload: MergePullRequestRequest,
    _: None = Depends(require_api_key),
) -> MergePullRequestResponse:
    repo_path = _get_connected_local_path_or_400()
    if not ensure_gh_available():
        raise HTTPException(status_code=400, detail="GitHub CLI (gh) is not available.")
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Merge requires explicit confirm=true for safety.",
        )

    try:
        merge_pr(repo_path, payload.pull_request_number, payload.merge_method)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to merge PR: {exc}") from exc

    add_task_event(
        "system",
        "pr_merged",
        f"PR #{payload.pull_request_number} merged using {payload.merge_method}",
    )
    return MergePullRequestResponse(
        pull_request_number=payload.pull_request_number,
        merged=True,
        message=f"PR #{payload.pull_request_number} merged successfully.",
    )


@app.post("/api/tasks/{task_id}/dispatch", response_model=DispatchTaskResponse)
def dispatch_task(
    task_id: str,
    payload: DispatchTaskRequest,
    _: None = Depends(require_api_key),
) -> DispatchTaskResponse:
    task = _get_task_or_404(task_id)
    repo_path = None
    if get_value("connected_mode") == "local":
        repo_path = get_value("connected_path")
    if repo_path and ensure_git_repo(repo_path):
        branch = task.branch_name or create_feature_branch(task.task_id)
        checkout_task_branch(repo_path, branch)
    try:
        result = dispatch_task_to_provider(task, payload.provider, payload.mode, repo_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    add_task_event(
        task_id,
        "task_dispatched",
        (
            f"Provider={result.provider} mode={result.mode_used}: {result.output}"
            + (
                f" | flow: {' ; '.join(result.command_flow)}"
                if result.command_flow
                else ""
            )
        ),
    )
    latest = _get_task_or_404(task_id)
    latest.execution_log.append(result.output)
    if result.command_flow:
        latest.execution_log.append(
            f"[dispatch-flow] {result.provider}: " + " | ".join(result.command_flow)
        )
    save_task(latest)
    return result


@app.post("/api/tasks/{task_id}/dispatch-many", response_model=DispatchManyTaskResponse)
def dispatch_task_many(
    task_id: str,
    payload: DispatchManyTaskRequest,
    _: None = Depends(require_api_key),
) -> DispatchManyTaskResponse:
    task = _get_task_or_404(task_id)
    repo_path = None
    if get_value("connected_mode") == "local":
        repo_path = get_value("connected_path")
    if repo_path and ensure_git_repo(repo_path):
        branch = task.branch_name or create_feature_branch(task.task_id)
        checkout_task_branch(repo_path, branch)
    seen: set[str] = set()
    normalized_providers: list[str] = []
    for provider in payload.providers:
        key = provider.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized_providers.append(key)

    if not normalized_providers:
        raise HTTPException(status_code=400, detail="No valid providers provided.")

    results: list[DispatchTaskResponse] = []
    log_lines: list[str] = []
    for provider in normalized_providers:
        try:
            result = dispatch_task_to_provider(task, provider, payload.mode, repo_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        add_task_event(
            task_id,
            "task_dispatched",
            (
                f"Provider={result.provider} mode={result.mode_used}: {result.output}"
                + (
                    f" | flow: {' ; '.join(result.command_flow)}"
                    if result.command_flow
                    else ""
                )
            ),
        )
        log_lines.append(
            f"[multi-dispatch] Provider={result.provider} mode={result.mode_used}: {result.output}"
        )
        if result.command_flow:
            log_lines.append(
                f"[multi-dispatch-flow] {result.provider}: "
                + " | ".join(result.command_flow)
            )
        results.append(result)

    latest = _get_task_or_404(task_id)
    latest.execution_log.extend(log_lines)
    save_task(latest)
    return DispatchManyTaskResponse(task_id=task_id, mode=payload.mode, results=results)


@app.post("/api/tasks/{task_id}/jobs", response_model=EnqueueJobResponse)
def enqueue_task_job(
    task_id: str,
    payload: EnqueueJobRequest,
    _: None = Depends(require_api_key),
) -> EnqueueJobResponse:
    _get_task_or_404(task_id)
    job = TaskJob(
        job_id=uuid4().hex[:10],
        task_id=task_id,
        job_type=payload.job_type,
        status=JobStatus.QUEUED,
        params=payload.params,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    save_task_job(job)
    add_task_event(task_id, "job_queued", f"Job {job.job_id} queued ({job.job_type}).")
    JOB_QUEUE.put(job.job_id)
    return EnqueueJobResponse(job_id=job.job_id, status=job.status)


@app.get("/api/jobs/{job_id}", response_model=TaskJob)
def get_task_job(job_id: str, _: None = Depends(require_api_key)) -> TaskJob:
    return _get_job_or_404(job_id)


@app.post("/api/projects/connect", response_model=ConnectProjectResponse)
def connect_project(
    payload: ConnectProjectRequest, _: None = Depends(require_api_key)
) -> ConnectProjectResponse:
    checks = run_preflight(payload)
    if payload.project_type.value == "ssh":
        target = get_ssh_target(payload)
        if payload.ssh_user:
            set_value("connected_ssh_user", payload.ssh_user)
        if payload.ssh_host:
            set_value("connected_ssh_host", payload.ssh_host)
        if payload.ssh_project_path:
            set_value("connected_ssh_path", payload.ssh_project_path)
        set_value("connected_mode", "ssh")
        response = ConnectProjectResponse(
            connected=True,
            summary=f"Connected in SSH mode to {target} (preflight is basic in MVP).",
            checks=checks,
        )
        add_task_event("system", "project_connected", response.summary)
        return response

    local_ok = all("yes" in line for line in checks[:2]) if checks else False
    if local_ok and payload.local_path:
        set_value("connected_mode", "local")
        set_value("connected_path", payload.local_path)
    response = ConnectProjectResponse(
        connected=local_ok,
        summary="Local project looks ready." if local_ok else "Local project needs fixes.",
        checks=checks,
    )
    add_task_event("system", "project_connected", response.summary)
    return response


@app.post("/api/tasks", response_model=TaskState)
def create_task(payload: TaskRequest, _: None = Depends(require_api_key)) -> TaskState:
    task_id = uuid4().hex[:8]
    task = TaskState(
        task_id=task_id,
        project_label=payload.project_label,
        user_goal=payload.user_goal,
        status=TaskStatus.PLANNING,
        plan=build_plan(payload.user_goal),
        manager_notes=f"Feature branch: {create_feature_branch(task_id)}",
        branch_name=create_feature_branch(task_id),
    )
    save_task(task)
    add_task_event(task.task_id, "task_created", f"Task created for goal: {payload.user_goal}")
    return task


@app.post("/api/tasks/{task_id}/advance", response_model=TaskState)
def advance_task_state(task_id: str, _: None = Depends(require_api_key)) -> TaskState:
    task = _get_task_or_404(task_id)
    updated = advance_task(task)
    save_task(updated)
    add_task_event(task_id, "task_advanced", f"Task moved to status: {updated.status.value}")
    return updated


@app.get("/api/tasks/{task_id}", response_model=TaskState)
def get_task(task_id: str, _: None = Depends(require_api_key)) -> TaskState:
    return _get_task_or_404(task_id)


@app.post("/api/tasks/{task_id}/execute-local", response_model=TaskState)
def execute_task_local(task_id: str, _: None = Depends(require_api_key)) -> TaskState:
    task = _get_task_or_404(task_id)
    repo_path = _get_connected_local_path_or_400()
    if not ensure_git_repo(repo_path):
        raise HTTPException(status_code=400, detail="Connected local path is not a git repo")

    branch = task.branch_name or create_feature_branch(task.task_id)
    checkout_task_branch(repo_path, branch)
    note_file = write_task_note(repo_path, task.task_id, task.user_goal)

    test_command = detect_test_command(repo_path)
    if test_command:
        code, out = run_shell(repo_path, test_command)
        task.tests_status = "passing" if code == 0 else "failing"
        task.execution_log.append(f"Ran tests: {test_command}")
        task.execution_log.append(out[-2000:] if out else "(no test output)")
        if code != 0:
            task.status = TaskStatus.NEEDS_REVIEW
            task.manager_notes = "Tests failed. Review output and request fixes."
    else:
        task.tests_status = "skipped"
        task.execution_log.append("No standard test command detected.")

    files = changed_files(repo_path)
    task.changed_files = files if files else [note_file]
    task.diff_preview = diff_preview(repo_path)
    task.status = TaskStatus.READY if task.tests_status != "failing" else TaskStatus.NEEDS_REVIEW
    task.manager_notes = (
        "Local execution completed. Review diff and merge when ready."
        if task.status == TaskStatus.READY
        else task.manager_notes
    )
    save_task(task)
    add_task_event(
        task_id,
        "task_executed_local",
        f"Local execution complete with tests_status={task.tests_status}",
    )
    return task


@app.post("/api/tasks/{task_id}/commit", response_model=TaskState)
def commit_task_changes(task_id: str, _: None = Depends(require_api_key)) -> TaskState:
    task = _get_task_or_404(task_id)
    repo_path = _get_connected_local_path_or_400()
    if not ensure_git_repo(repo_path):
        raise HTTPException(status_code=400, detail="Connected local path is not a git repo")

    branch = task.branch_name or create_feature_branch(task.task_id)
    checkout_task_branch(repo_path, branch)

    stage_all(repo_path)
    if not has_staged_changes(repo_path):
        task.manager_notes = "No new changes to commit."
        save_task(task)
        add_task_event(task_id, "task_commit_skipped", "No staged changes to commit.")
        return task

    message = f"feat: complete task {task.task_id}\n\nGoal: {task.user_goal}"
    sha = commit_staged(repo_path, message)
    task.commit_hash = sha
    task.manager_notes = f"Committed on {branch} at {sha}. Ready for PR draft."
    save_task(task)
    add_task_event(task_id, "task_committed", f"Commit created: {sha}")
    return task


@app.get("/api/tasks/{task_id}/prepare-pr", response_model=PreparePrResponse)
def prepare_pr(task_id: str, _: None = Depends(require_api_key)) -> PreparePrResponse:
    task = _get_task_or_404(task_id)

    branch = task.branch_name or create_feature_branch(task.task_id)
    title = f"[AI Task] {task.project_label}: {task.user_goal[:60]}"
    body = (
        "## Summary\n"
        f"- Goal: {task.user_goal}\n"
        f"- Status: {task.status.value}\n"
        f"- Tests: {task.tests_status}\n"
        f"- Branch: `{branch}`\n"
        f"- Commit: `{task.commit_hash or 'not committed yet'}`\n\n"
        "## Changed Files\n"
        + "\n".join([f"- `{f}`" for f in task.changed_files] or ["- none"])
        + "\n\n## Manager Notes\n"
        + (task.manager_notes or "No manager notes.")
    )
    return PreparePrResponse(
        task_id=task.task_id,
        branch_name=branch,
        title=title,
        body=body,
    )


@app.post("/api/tasks/{task_id}/create-pr", response_model=CreatePrResponse)
def create_task_pr(
    task_id: str, payload: CreatePrRequest, _: None = Depends(require_api_key)
) -> CreatePrResponse:
    task = _get_task_or_404(task_id)
    repo_path = _get_connected_local_path_or_400()
    if not ensure_git_repo(repo_path):
        raise HTTPException(status_code=400, detail="Connected local path is not a git repo")
    if not ensure_gh_available():
        raise HTTPException(
            status_code=400,
            detail="GitHub CLI (gh) is not available. Install and run gh auth login.",
        )

    pr_draft = prepare_pr(task_id)
    branch = pr_draft.branch_name
    checkout_task_branch(repo_path, branch)

    try:
        push_branch(repo_path, branch)
        pr_url = create_pr(
            repo_path=repo_path,
            title=pr_draft.title,
            body=pr_draft.body,
            head_branch=branch,
            base_branch=payload.base_branch,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to create PR. Check gh auth and remote settings. {exc}",
        ) from exc

    task.manager_notes = f"PR created successfully: {pr_url}"
    save_task(task)
    add_task_event(task_id, "pr_created", f"PR URL: {pr_url}")
    return CreatePrResponse(task_id=task.task_id, pull_request_url=pr_url)


@app.post("/api/tasks/{task_id}/run-all", response_model=RunAllResponse)
def run_all(
    task_id: str, payload: RunAllRequest, _: None = Depends(require_api_key)
) -> RunAllResponse:
    _get_task_or_404(task_id)

    execute_task_local(task_id)
    task = _get_task_or_404(task_id)
    if task.tests_status == "failing":
        return RunAllResponse(
            task_id=task_id,
            status="needs_review",
            summary="Stopped because tests failed during local execution.",
        )

    commit_task_changes(task_id)
    task = _get_task_or_404(task_id)
    if not task.commit_hash:
        return RunAllResponse(
            task_id=task_id,
            status="ready",
            summary="Execution finished, but no new changes were committed.",
        )

    pr_result = create_task_pr(task_id, CreatePrRequest(base_branch=payload.base_branch))
    return RunAllResponse(
        task_id=task_id,
        status="completed",
        summary="Run-all completed: executed, committed, and opened a GitHub PR.",
        pull_request_url=pr_result.pull_request_url,
    )


@app.post("/api/tasks/{task_id}/fix-it", response_model=TaskState)
def fix_it_for_me(task_id: str, _: None = Depends(require_api_key)) -> TaskState:
    task = _get_task_or_404(task_id)
    if task.tests_status != "failing":
        raise HTTPException(
            status_code=400,
            detail="Fix It For Me is only available after a failing test run.",
        )

    failure_log = task.execution_log[-1] if task.execution_log else "No failure logs found."
    followup_goal = (
        "Fix failing tests and code issues from previous run.\n\n"
        f"Original goal: {task.user_goal}\n\n"
        f"Failure context:\n{failure_log[:1200]}"
    )
    followup_id = uuid4().hex[:8]
    followup_task = TaskState(
        task_id=followup_id,
        project_label=task.project_label,
        user_goal=followup_goal,
        status=TaskStatus.PLANNING,
        plan=build_plan(followup_goal),
        manager_notes=(
            "Auto-generated recovery task from test failure. "
            f"Feature branch: {create_feature_branch(followup_id)}"
        ),
        branch_name=create_feature_branch(followup_id),
    )
    save_task(followup_task)
    add_task_event(
        followup_id,
        "task_recovery_created",
        f"Recovery task created from failing task {task_id}",
    )
    return followup_task


@app.get("/api/tasks/{task_id}/events", response_model=list[TaskEvent])
def get_task_events(task_id: str, _: None = Depends(require_api_key)) -> list[TaskEvent]:
    _get_task_or_404(task_id)
    return list_task_events(task_id)


@app.post("/api/tasks/{task_id}/execute-ssh", response_model=ExecuteSshResponse)
def execute_task_ssh(
    task_id: str,
    payload: ExecuteSshRequest,
    _: None = Depends(require_api_key),
) -> ExecuteSshResponse:
    task = _get_task_or_404(task_id)
    ssh_user, ssh_host, ssh_path = _get_connected_ssh_or_400()
    remote_cmd = f"cd {ssh_path} && {payload.command}"
    exit_code, output = run_remote_command(
        ssh_user=ssh_user,
        ssh_host=ssh_host,
        command=remote_cmd,
        timeout_seconds=payload.timeout_seconds,
    )
    success = exit_code == 0
    task.execution_log.append(
        f"SSH [{ssh_user}@{ssh_host}] command: {payload.command}\n{output[-2000:]}"
    )
    task.manager_notes = (
        "Remote SSH command completed successfully."
        if success
        else "Remote SSH command failed. Review output."
    )
    save_task(task)
    add_task_event(
        task_id,
        "task_executed_ssh",
        f"SSH command exit_code={exit_code} command={payload.command}",
    )
    return ExecuteSshResponse(
        task_id=task_id,
        success=success,
        exit_code=exit_code,
        output=output,
    )
