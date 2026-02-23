"""Authorization helpers for Takeoff."""

from src.config import Settings


def is_authorized(slack_user_id: str, settings: Settings) -> bool:
    """Return True if the given Slack user ID is allowed to trigger merges.

    An empty authorized list means no one is allowed (fail-safe default).
    """
    authorized = settings.authorized_user_ids
    if not authorized:
        return False
    return slack_user_id in authorized
