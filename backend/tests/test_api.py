import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

TEST_DB = Path("/tmp/agent_orch_test.db")
os.environ["AGENT_ORCH_DB_PATH"] = str(TEST_DB)
os.environ["AGENT_ORCH_API_KEY"] = "test-key"
os.environ["AGENT_ORCH_PREVIOUS_API_KEY"] = "old-key"
os.environ["AGENT_ORCH_RATE_LIMIT_PER_MIN"] = "8"

from app.main import app, reset_rate_limit_state


def _reset_db() -> None:
    if TEST_DB.exists():
        TEST_DB.unlink()
    reset_rate_limit_state()


def _headers() -> dict[str, str]:
    return {"x-api-key": "test-key"}


def test_health() -> None:
    _reset_db()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_create_and_fetch_task() -> None:
    _reset_db()
    with TestClient(app) as client:
        payload = {"project_label": "Demo", "user_goal": "Add login"}
        created = client.post("/api/tasks", json=payload, headers=_headers())
        assert created.status_code == 200
        task_id = created.json()["task_id"]

        fetched = client.get(f"/api/tasks/{task_id}", headers=_headers())
        assert fetched.status_code == 200
        assert fetched.json()["project_label"] == "Demo"
        assert fetched.json()["user_goal"] == "Add login"

        events = client.get(f"/api/tasks/{task_id}/events", headers=_headers())
        assert events.status_code == 200
        event_list = events.json()
        assert len(event_list) >= 1
        assert event_list[0]["event_type"] == "task_created"


def test_auth_required_on_api() -> None:
    _reset_db()
    with TestClient(app) as client:
        payload = {"project_label": "Demo", "user_goal": "Add login"}
        response = client.post("/api/tasks", json=payload)
        assert response.status_code == 401


def test_previous_api_key_is_accepted() -> None:
    _reset_db()
    with TestClient(app) as client:
        payload = {"project_label": "Demo", "user_goal": "Add login"}
        response = client.post(
            "/api/tasks",
            json=payload,
            headers={"x-api-key": "old-key"},
        )
        assert response.status_code == 200


def test_request_id_header_is_returned() -> None:
    _reset_db()
    with TestClient(app) as client:
        payload = {"project_label": "Demo", "user_goal": "Add login"}
        response = client.post(
            "/api/tasks",
            json=payload,
            headers={"x-api-key": "test-key", "x-request-id": "abc-123"},
        )
        assert response.status_code == 200
        assert response.headers.get("x-request-id") == "abc-123"


def test_rate_limit_is_enforced() -> None:
    _reset_db()
    with TestClient(app) as client:
        payload = {"project_label": "Demo", "user_goal": "Add login"}
        for _ in range(8):
            ok = client.post("/api/tasks", json=payload, headers=_headers())
            assert ok.status_code == 200
        limited = client.post("/api/tasks", json=payload, headers=_headers())
        assert limited.status_code == 429


def test_providers_endpoint_requires_auth_and_returns_list() -> None:
    _reset_db()
    with TestClient(app) as client:
        denied = client.get("/api/providers")
        assert denied.status_code == 401

        allowed = client.get("/api/providers", headers=_headers())
        assert allowed.status_code == 200
        body = allowed.json()
        assert "providers" in body
        assert isinstance(body["providers"], list)


def test_dispatch_endpoint_records_event() -> None:
    _reset_db()
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"project_label": "Demo", "user_goal": "Add login"},
            headers=_headers(),
        )
        task_id = created.json()["task_id"]

        dispatched = client.post(
            f"/api/tasks/{task_id}/dispatch",
            json={"provider": "codex", "mode": "api"},
            headers=_headers(),
        )
        assert dispatched.status_code == 200
        body = dispatched.json()
        assert body["provider"] == "codex"
        assert body["mode_used"] == "api"

        events = client.get(f"/api/tasks/{task_id}/events", headers=_headers())
        assert events.status_code == 200
        assert any(e["event_type"] == "task_dispatched" for e in events.json())


def test_unhandled_error_returns_request_id(monkeypatch) -> None:
    _reset_db()

    def _explode(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.main.save_task", _explode)
    with TestClient(app) as client:
        payload = {"project_label": "Demo", "user_goal": "Add login"}
        response = client.post("/api/tasks", json=payload, headers=_headers())
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "Internal server error"
        assert "request_id" in body
        assert response.headers.get("x-request-id")


def test_execute_ssh_uses_connected_ssh_target(monkeypatch) -> None:
    _reset_db()

    def _fake_run_remote_command(ssh_user, ssh_host, command, timeout_seconds):
        assert ssh_user == "ubuntu"
        assert ssh_host == "example.com"
        assert "cd /srv/app && pwd" in command
        assert timeout_seconds == 12
        return 0, "/srv/app"

    monkeypatch.setattr("app.main.run_remote_command", _fake_run_remote_command)
    with TestClient(app) as client:
        connect = client.post(
            "/api/projects/connect",
            json={
                "project_type": "ssh",
                "ssh_user": "ubuntu",
                "ssh_host": "example.com",
                "ssh_project_path": "/srv/app",
            },
            headers=_headers(),
        )
        assert connect.status_code == 200

        created = client.post(
            "/api/tasks",
            json={"project_label": "Demo", "user_goal": "Run remote pwd"},
            headers=_headers(),
        )
        task_id = created.json()["task_id"]
        executed = client.post(
            f"/api/tasks/{task_id}/execute-ssh",
            json={"command": "pwd", "timeout_seconds": 12},
            headers=_headers(),
        )
        assert executed.status_code == 200
        body = executed.json()
        assert body["success"] is True
        assert body["exit_code"] == 0


def test_enqueue_and_poll_job() -> None:
    _reset_db()
    with TestClient(app) as client:
        created = client.post(
            "/api/tasks",
            json={"project_label": "Demo", "user_goal": "Dispatch via queue"},
            headers=_headers(),
        )
        task_id = created.json()["task_id"]

        enq = client.post(
            f"/api/tasks/{task_id}/jobs",
            json={"job_type": "dispatch", "params": {"provider": "codex", "mode": "api"}},
            headers=_headers(),
        )
        assert enq.status_code == 200
        job_id = enq.json()["job_id"]

        status = None
        for _ in range(20):
            job = client.get(f"/api/jobs/{job_id}", headers=_headers())
            assert job.status_code == 200
            status = job.json()["status"]
            if status in ("succeeded", "failed"):
                break
            time.sleep(0.05)

        assert status == "succeeded"


def test_github_pr_status_endpoint(monkeypatch) -> None:
    _reset_db()

    monkeypatch.setattr("app.main.ensure_gh_available", lambda: True)
    monkeypatch.setattr(
        "app.main.get_pr_status",
        lambda repo_path, pull_request_number: {
            "number": pull_request_number,
            "url": "https://github.com/org/repo/pull/12",
            "state": "OPEN",
            "mergeable": "MERGEABLE",
            "isDraft": False,
        },
    )
    with TestClient(app) as client:
        connect = client.post(
            "/api/projects/connect",
            json={"project_type": "local", "local_path": "/tmp"},
            headers=_headers(),
        )
        assert connect.status_code == 200
        status = client.post(
            "/api/github/pr-status",
            json={"pull_request_number": 12},
            headers=_headers(),
        )
        assert status.status_code == 200
        assert status.json()["pull_request_number"] == 12


def test_github_merge_requires_confirm(monkeypatch) -> None:
    _reset_db()
    monkeypatch.setattr("app.main.ensure_gh_available", lambda: True)
    with TestClient(app) as client:
        connect = client.post(
            "/api/projects/connect",
            json={"project_type": "local", "local_path": "/tmp"},
            headers=_headers(),
        )
        assert connect.status_code == 200
        response = client.post(
            "/api/github/merge-pr",
            json={"pull_request_number": 5, "merge_method": "squash", "confirm": False},
            headers=_headers(),
        )
        assert response.status_code == 400
