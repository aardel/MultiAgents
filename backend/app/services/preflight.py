from pathlib import Path

from app.models import ConnectProjectRequest, ProjectType


def run_preflight(request: ConnectProjectRequest) -> list[str]:
    checks: list[str] = []

    if request.project_type == ProjectType.LOCAL:
        if not request.local_path:
            checks.append("Missing local path")
            return checks

        p = Path(request.local_path)
        checks.append(f"Path exists: {'yes' if p.exists() else 'no'}")
        checks.append(f"Path is directory: {'yes' if p.is_dir() else 'no'}")
        checks.append(f"Git folder present: {'yes' if (p / '.git').exists() else 'no'}")
        return checks

    # SSH mode preflight is intentionally simple in MVP.
    checks.append(f"SSH host provided: {'yes' if request.ssh_host else 'no'}")
    checks.append(f"SSH user provided: {'yes' if request.ssh_user else 'no'}")
    checks.append(
        f"SSH project path provided: {'yes' if request.ssh_project_path else 'no'}"
    )
    checks.append("Remote runtime checks: pending (phase 2)")
    return checks
