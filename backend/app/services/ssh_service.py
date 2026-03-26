from app.models import ConnectProjectRequest
import subprocess


def get_ssh_target(request: ConnectProjectRequest) -> str:
    user = request.ssh_user or "unknown-user"
    host = request.ssh_host or "unknown-host"
    path = request.ssh_project_path or "~"
    return f"{user}@{host}:{path}"


def run_remote_command(
    ssh_user: str,
    ssh_host: str,
    command: str,
    timeout_seconds: int = 60,
) -> tuple[int, str]:
    target = f"{ssh_user}@{ssh_host}"
    completed = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            target,
            command,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    return completed.returncode, output
