import os
import shutil

from app.models import ProviderStatus


PROVIDER_SPECS = [
    ("claude", "claude", "ANTHROPIC_API_KEY"),
    ("codex", "codex", "OPENAI_API_KEY"),
    ("gemini", "gemini", "GEMINI_API_KEY"),
    ("openai", "openai", "OPENAI_API_KEY"),
    ("copilot", "gh", "GITHUB_TOKEN"),
    ("cursor", "cursor-agent", "CURSOR_API_KEY"),
]


def get_provider_statuses() -> list[ProviderStatus]:
    statuses: list[ProviderStatus] = []
    for provider, cli, env_key in PROVIDER_SPECS:
        cli_available = shutil.which(cli) is not None
        api_key_configured = bool(os.environ.get(env_key, "").strip())
        recommended_mode = (
            "cli"
            if cli_available
            else ("api" if api_key_configured else "not_configured")
        )
        statuses.append(
            ProviderStatus(
                provider=provider,
                cli_available=cli_available,
                api_key_configured=api_key_configured,
                recommended_mode=recommended_mode,
            )
        )
    return statuses
