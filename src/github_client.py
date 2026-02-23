"""GitHub API client for merging pull requests."""

from dataclasses import dataclass
from enum import Enum

import httpx

GITHUB_API_BASE = "https://api.github.com"


class MergeStatus(Enum):
    """Possible outcomes of a merge attempt."""

    SUCCESS = "success"
    ALREADY_MERGED = "already_merged"
    CONFLICT = "conflict"
    CHECKS_PENDING = "checks_pending"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass
class MergeResult:
    """Result returned after a merge attempt."""

    status: MergeStatus
    message: str


async def merge_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
    github_token: str,
) -> MergeResult:
    """Attempt to merge a GitHub pull request.

    Returns a MergeResult describing the outcome. Never raises — all GitHub
    API errors are captured and surfaced via MergeResult.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/merge"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Check PR state before attempting merge
        pr_state = await _get_pr_state(client, owner, repo, pull_number, headers)
        if pr_state is not None:
            return pr_state

        response = await client.put(url, headers=headers, json={"merge_method": "squash"})

    return _parse_merge_response(response, pull_number)


async def _get_pr_state(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    pull_number: int,
    headers: dict[str, str],
) -> MergeResult | None:
    """Return a MergeResult if the PR is in a non-mergeable state, else None."""
    pr_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}"
    response = await client.get(pr_url, headers=headers)

    if response.status_code == 404:
        return MergeResult(
            status=MergeStatus.NOT_FOUND,
            message=f"PR #{pull_number} not found in {owner}/{repo}.",
        )

    if response.status_code != 200:
        return MergeResult(
            status=MergeStatus.ERROR,
            message=f"Failed to fetch PR #{pull_number}: HTTP {response.status_code}.",
        )

    data = response.json()

    if data.get("merged"):
        return MergeResult(
            status=MergeStatus.ALREADY_MERGED,
            message=f"PR #{pull_number} is already merged.",
        )

    if data.get("state") == "closed":
        return MergeResult(
            status=MergeStatus.ERROR,
            message=f"PR #{pull_number} is closed without being merged.",
        )

    # mergeable can be null while GitHub computes it; treat as potentially ok
    mergeable = data.get("mergeable")
    if mergeable is False:
        return MergeResult(
            status=MergeStatus.CONFLICT,
            message=f"Cannot merge PR #{pull_number} — there are merge conflicts.",
        )

    return None


def _parse_merge_response(response: httpx.Response, pull_number: int) -> MergeResult:
    """Map a GitHub merge API response to a MergeResult."""
    if response.status_code == 200:
        return MergeResult(
            status=MergeStatus.SUCCESS,
            message=f"PR #{pull_number} merged successfully.",
        )

    body: dict[str, object] = {}
    try:
        body = response.json()
    except Exception:
        pass

    github_message = str(body.get("message", "")).lower()

    if response.status_code == 405:
        if "not mergeable" in github_message or "conflict" in github_message:
            return MergeResult(
                status=MergeStatus.CONFLICT,
                message=f"Cannot merge PR #{pull_number} — there are merge conflicts.",
            )
        return MergeResult(
            status=MergeStatus.CHECKS_PENDING,
            message=f"Cannot merge PR #{pull_number} — status checks have not passed.",
        )

    if response.status_code == 409:
        return MergeResult(
            status=MergeStatus.CONFLICT,
            message=f"Cannot merge PR #{pull_number} — there are merge conflicts.",
        )

    if response.status_code == 404:
        return MergeResult(
            status=MergeStatus.NOT_FOUND,
            message=f"PR #{pull_number} not found.",
        )

    reason = body.get("message") or f"HTTP {response.status_code}"
    return MergeResult(
        status=MergeStatus.ERROR,
        message=f"Failed to merge PR #{pull_number}: {reason}",
    )
