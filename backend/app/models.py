from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProjectType(str, Enum):
    LOCAL = "local"
    SSH = "ssh"


class ConnectProjectRequest(BaseModel):
    project_type: ProjectType
    local_path: Optional[str] = None
    ssh_host: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_project_path: Optional[str] = None


class ConnectProjectResponse(BaseModel):
    connected: bool
    summary: str
    checks: list[str]


class TaskRequest(BaseModel):
    user_goal: str = Field(min_length=4, max_length=500)
    project_label: str = Field(min_length=1, max_length=120)
    test_command: Optional[str] = None


class TaskStatus(str, Enum):
    PLANNING = "planning"
    WORKING = "working"
    NEEDS_REVIEW = "needs_review"
    READY = "ready"
    FAILED = "failed"


class TaskState(BaseModel):
    task_id: str
    project_label: str
    user_goal: str
    status: TaskStatus
    plan: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    tests_status: str = "not_run"
    manager_notes: str = ""
    branch_name: Optional[str] = None
    execution_log: list[str] = Field(default_factory=list)
    diff_preview: str = ""
    commit_hash: Optional[str] = None


class PreparePrResponse(BaseModel):
    task_id: str
    branch_name: str
    title: str
    body: str


class CreatePrRequest(BaseModel):
    base_branch: str = "main"


class CreatePrResponse(BaseModel):
    task_id: str
    pull_request_url: str


class RunAllRequest(BaseModel):
    base_branch: str = "main"


class RunAllResponse(BaseModel):
    task_id: str
    status: str
    summary: str
    pull_request_url: Optional[str] = None


class TaskEvent(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    message: str
    created_at: str


class ProviderStatus(BaseModel):
    provider: str
    cli_available: bool
    api_key_configured: bool
    recommended_mode: str


class ProvidersResponse(BaseModel):
    providers: list[ProviderStatus]


class DispatchTaskRequest(BaseModel):
    provider: str
    mode: str = "auto"


class DispatchTaskResponse(BaseModel):
    task_id: str
    provider: str
    mode_used: str
    output: str


class ExecuteSshRequest(BaseModel):
    command: str = "pwd"
    timeout_seconds: int = 60


class ExecuteSshResponse(BaseModel):
    task_id: str
    success: bool
    exit_code: int
    output: str


class PullRequestStatusRequest(BaseModel):
    pull_request_number: int


class PullRequestStatusResponse(BaseModel):
    pull_request_number: int
    url: str
    state: str
    mergeable: str
    is_draft: bool


class MergePullRequestRequest(BaseModel):
    pull_request_number: int
    merge_method: str = "squash"
    confirm: bool = False


class MergePullRequestResponse(BaseModel):
    pull_request_number: int
    merged: bool
    message: str
