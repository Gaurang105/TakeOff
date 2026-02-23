"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration values for Takeoff, sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Slack credentials
    slack_bot_token: str
    slack_signing_secret: str

    # GitHub credentials
    github_token: str

    # Comma-separated list of Slack user IDs allowed to trigger merges
    # e.g. "U012AB3CD,U056EF7GH"
    authorized_slack_user_ids: str = ""

    @property
    def authorized_user_ids(self) -> set[str]:
        """Return the authorized Slack user IDs as a set."""
        return {
            uid.strip()
            for uid in self.authorized_slack_user_ids.split(",")
            if uid.strip()
        }


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton of Settings."""
    return Settings()
