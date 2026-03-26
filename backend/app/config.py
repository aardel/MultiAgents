import os


def app_env() -> str:
    return os.environ.get("AGENT_ORCH_ENV", "development").strip().lower()


def api_key() -> str:
    value = os.environ.get("AGENT_ORCH_API_KEY", "").strip()
    if value:
        return value
    if app_env() == "development":
        return "dev-key"
    raise RuntimeError("AGENT_ORCH_API_KEY is required outside development.")


def previous_api_key() -> str:
    return os.environ.get("AGENT_ORCH_PREVIOUS_API_KEY", "").strip()


def allowed_origins() -> list[str]:
    raw = os.environ.get("AGENT_ORCH_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if app_env() == "development":
        return ["*"]
    # Safe fallback for production-like mode.
    return []


def validate_runtime_config() -> None:
    # Ensures production-like environments fail fast when secrets are missing.
    _ = api_key()
    if app_env() != "development" and not allowed_origins():
        raise RuntimeError("AGENT_ORCH_ALLOWED_ORIGINS is required outside development.")
