"""Slack event parsing, signature verification, and merge dispatch."""

import hashlib
import hmac
import logging
import re
import time
from dataclasses import dataclass

from slack_sdk.web.async_client import AsyncWebClient

from src.auth import is_authorized
from src.config import Settings
from src.github_client import MergeStatus, merge_pull_request

logger = logging.getLogger(__name__)

# Matches https://github.com/{owner}/{repo}/pull/{number}
_PR_URL_PATTERN = re.compile(
    r"https://github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)/pull/(\d+)"
)

# Keywords that signal an intent to merge
_MERGE_KEYWORDS = re.compile(r"\bmerge\b|can\s+u|please\s+merge", re.IGNORECASE)


@dataclass
class ParsedPR:
    """Extracted pull request coordinates from a Slack message."""

    owner: str
    repo: str
    pull_number: int
    url: str


def verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
) -> bool:
    """Return True if the request signature matches the signing secret.

    Rejects requests older than 5 minutes to prevent replay attacks.
    """
    try:
        request_time = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - request_time) > 300:
        return False

    base_string = f"v0:{timestamp}:{body.decode('utf-8')}"
    expected = (
        "v0="
        + hmac.new(
            signing_secret.encode("utf-8"),
            base_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


def extract_pr(text: str) -> ParsedPR | None:
    """Return a ParsedPR if the message contains a GitHub PR URL, else None."""
    match = _PR_URL_PATTERN.search(text)
    if not match:
        return None
    owner, repo, number = match.groups()
    return ParsedPR(
        owner=owner,
        repo=repo,
        pull_number=int(number),
        url=match.group(0),
    )


def has_merge_intent(text: str) -> bool:
    """Return True if the message text expresses an intent to merge."""
    return bool(_MERGE_KEYWORDS.search(text))


async def handle_message_event(event: dict[str, object], settings: Settings) -> None:
    """Process a Slack message event and merge the PR if all conditions are met.

    Conditions:
    - Message is not from a bot
    - Message contains a GitHub PR URL
    - Message contains merge-intent keywords
    - Sending user is authorized
    """
    # Ignore bot messages to avoid loops
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return

    text = str(event.get("text") or "")
    channel = str(event.get("channel") or "")
    thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
    user_id = str(event.get("user") or "")

    pr = extract_pr(text)
    if pr is None:
        return

    if not has_merge_intent(text):
        return

    slack_client = AsyncWebClient(token=settings.slack_bot_token)

    if not is_authorized(user_id, settings):
        await slack_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="Sorry, you're not authorized to trigger merges.",
        )
        return

    logger.info(
        "Merging PR #%d in %s/%s on behalf of Slack user %s",
        pr.pull_number,
        pr.owner,
        pr.repo,
        user_id,
    )

    result = await merge_pull_request(
        owner=pr.owner,
        repo=pr.repo,
        pull_number=pr.pull_number,
        github_token=settings.github_token,
    )

    icon = "✓" if result.status == MergeStatus.SUCCESS else "✗"
    await slack_client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=f"{icon} {result.message}",
    )
