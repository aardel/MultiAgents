import os

# Load repo-local `.env` (if present) so provider API keys can be configured
# without requiring manual `export` in every shell.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # If python-dotenv isn't available or parsing fails, fall back to existing env vars.
    pass


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
        origins = [item.strip() for item in raw.split(",") if item.strip()]
        # Always allow the local UI during development.
        if app_env() == "development":
            origins.extend(["http://127.0.0.1:5501", "http://localhost:5501"])
        # De-dup while preserving order.
        deduped = []
        seen = set()
        for o in origins:
            if o and o not in seen:
                seen.add(o)
                deduped.append(o)
        return deduped
    if app_env() == "development":
        # Use explicit local origins rather than "*" because we set
        # allow_credentials=True in the CORS middleware.
        return ["http://127.0.0.1:5501", "http://localhost:5501"]
    # Safe fallback for production-like mode.
    return []


def validate_runtime_config() -> None:
    # Ensures production-like environments fail fast when secrets are missing.
    _ = api_key()
    if app_env() != "development" and not allowed_origins():
        raise RuntimeError("AGENT_ORCH_ALLOWED_ORIGINS is required outside development.")
