"""Tests for github_client: merge outcomes based on GitHub API responses."""

import pytest
import respx
import httpx

from src.github_client import MergeStatus, merge_pull_request

OWNER = "headout"
REPO = "backend"
PR = 42
TOKEN = "ghp_test"

PR_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/pulls/{PR}"
MERGE_URL = f"https://api.github.com/repos/{OWNER}/{REPO}/pulls/{PR}/merge"


def _open_pr_payload(mergeable: bool | None = True) -> dict:
    return {"state": "open", "merged": False, "mergeable": mergeable}


# ---------------------------------------------------------------------------
# Successful merge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_merge() -> None:
    with respx.mock:
        respx.get(PR_URL).mock(return_value=httpx.Response(200, json=_open_pr_payload()))
        respx.put(MERGE_URL).mock(return_value=httpx.Response(200, json={"sha": "abc", "merged": True}))

        result = await merge_pull_request(OWNER, REPO, PR, TOKEN)

    assert result.status == MergeStatus.SUCCESS
    assert str(PR) in result.message


# ---------------------------------------------------------------------------
# Already merged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_already_merged() -> None:
    payload = {"state": "closed", "merged": True, "mergeable": None}
    with respx.mock:
        respx.get(PR_URL).mock(return_value=httpx.Response(200, json=payload))

        result = await merge_pull_request(OWNER, REPO, PR, TOKEN)

    assert result.status == MergeStatus.ALREADY_MERGED


# ---------------------------------------------------------------------------
# Merge conflict detected in PR state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_from_pr_state() -> None:
    with respx.mock:
        respx.get(PR_URL).mock(return_value=httpx.Response(200, json=_open_pr_payload(mergeable=False)))

        result = await merge_pull_request(OWNER, REPO, PR, TOKEN)

    assert result.status == MergeStatus.CONFLICT


# ---------------------------------------------------------------------------
# Merge conflict returned by merge endpoint (405)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_from_merge_endpoint() -> None:
    with respx.mock:
        respx.get(PR_URL).mock(return_value=httpx.Response(200, json=_open_pr_payload()))
        respx.put(MERGE_URL).mock(
            return_value=httpx.Response(405, json={"message": "Pull Request is not mergeable"})
        )

        result = await merge_pull_request(OWNER, REPO, PR, TOKEN)

    assert result.status == MergeStatus.CONFLICT


# ---------------------------------------------------------------------------
# CI checks not passed (405)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checks_pending() -> None:
    with respx.mock:
        respx.get(PR_URL).mock(return_value=httpx.Response(200, json=_open_pr_payload()))
        respx.put(MERGE_URL).mock(
            return_value=httpx.Response(405, json={"message": "Required status checks failed"})
        )

        result = await merge_pull_request(OWNER, REPO, PR, TOKEN)

    assert result.status == MergeStatus.CHECKS_PENDING


# ---------------------------------------------------------------------------
# PR not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pr_not_found() -> None:
    with respx.mock:
        respx.get(PR_URL).mock(return_value=httpx.Response(404, json={"message": "Not Found"}))

        result = await merge_pull_request(OWNER, REPO, PR, TOKEN)

    assert result.status == MergeStatus.NOT_FOUND


# ---------------------------------------------------------------------------
# Unexpected error from GitHub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unexpected_error() -> None:
    with respx.mock:
        respx.get(PR_URL).mock(return_value=httpx.Response(200, json=_open_pr_payload()))
        respx.put(MERGE_URL).mock(
            return_value=httpx.Response(500, json={"message": "Internal Server Error"})
        )

        result = await merge_pull_request(OWNER, REPO, PR, TOKEN)

    assert result.status == MergeStatus.ERROR
    assert "500" in result.message or "Internal" in result.message
