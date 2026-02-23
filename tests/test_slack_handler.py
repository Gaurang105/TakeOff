"""Tests for slack_handler: signature verification, PR extraction, intent detection."""

import hashlib
import hmac
import time

import pytest

from src.config import Settings
from src.slack_handler import (
    extract_pr,
    has_merge_intent,
    verify_slack_signature,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SIGNING_SECRET = "test_signing_secret"


def _make_signature(body: bytes, timestamp: str, secret: str = SIGNING_SECRET) -> str:
    base = f"v0:{timestamp}:{body.decode()}"
    digest = hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _now_ts() -> str:
    return str(int(time.time()))


# ---------------------------------------------------------------------------
# verify_slack_signature
# ---------------------------------------------------------------------------


class TestVerifySlackSignature:
    def test_valid_signature(self) -> None:
        body = b"payload=test"
        ts = _now_ts()
        sig = _make_signature(body, ts)
        assert verify_slack_signature(body, ts, sig, SIGNING_SECRET) is True

    def test_invalid_signature(self) -> None:
        body = b"payload=test"
        ts = _now_ts()
        assert verify_slack_signature(body, ts, "v0=bad", SIGNING_SECRET) is False

    def test_replayed_request(self) -> None:
        body = b"payload=test"
        old_ts = str(int(time.time()) - 400)  # older than 5 minutes
        sig = _make_signature(body, old_ts)
        assert verify_slack_signature(body, old_ts, sig, SIGNING_SECRET) is False

    def test_non_numeric_timestamp(self) -> None:
        body = b"payload=test"
        assert verify_slack_signature(body, "notanumber", "v0=x", SIGNING_SECRET) is False

    def test_wrong_secret(self) -> None:
        body = b"payload=test"
        ts = _now_ts()
        sig = _make_signature(body, ts, secret="correct_secret")
        assert verify_slack_signature(body, ts, sig, "wrong_secret") is False


# ---------------------------------------------------------------------------
# extract_pr
# ---------------------------------------------------------------------------


class TestExtractPR:
    def test_extracts_standard_url(self) -> None:
        text = "Please merge https://github.com/headout/backend/pull/42"
        pr = extract_pr(text)
        assert pr is not None
        assert pr.owner == "headout"
        assert pr.repo == "backend"
        assert pr.pull_number == 42

    def test_returns_none_for_non_pr_url(self) -> None:
        assert extract_pr("https://github.com/headout/backend") is None

    def test_returns_none_for_no_url(self) -> None:
        assert extract_pr("just a plain message") is None

    def test_handles_hyphenated_repo_names(self) -> None:
        text = "merge https://github.com/my-org/my-repo/pull/100"
        pr = extract_pr(text)
        assert pr is not None
        assert pr.owner == "my-org"
        assert pr.repo == "my-repo"
        assert pr.pull_number == 100

    def test_url_stored_on_result(self) -> None:
        url = "https://github.com/headout/app/pull/7"
        pr = extract_pr(url)
        assert pr is not None
        assert pr.url == url


# ---------------------------------------------------------------------------
# has_merge_intent
# ---------------------------------------------------------------------------


class TestHasMergeIntent:
    @pytest.mark.parametrize(
        "text",
        [
            "please merge this when available",
            "merge https://github.com/org/repo/pull/1",
            "can u https://github.com/org/repo/pull/2",
            "Can U merge this?",
            "MERGE it now",
        ],
    )
    def test_detects_intent(self, text: str) -> None:
        assert has_merge_intent(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "LGTM, looks good to me",
            "approved",
            "left a comment",
        ],
    )
    def test_no_intent(self, text: str) -> None:
        assert has_merge_intent(text) is False


# ---------------------------------------------------------------------------
# Auth integration (via Settings)
# ---------------------------------------------------------------------------


class TestAuthorization:
    def _settings(self, user_ids: str) -> Settings:
        return Settings(
            slack_bot_token="xoxb-test",
            slack_signing_secret=SIGNING_SECRET,
            github_token="ghp_test",
            authorized_slack_user_ids=user_ids,
        )

    def test_authorized_user(self) -> None:
        from src.auth import is_authorized

        settings = self._settings("U111,U222")
        assert is_authorized("U111", settings) is True

    def test_unauthorized_user(self) -> None:
        from src.auth import is_authorized

        settings = self._settings("U111,U222")
        assert is_authorized("U999", settings) is False

    def test_empty_allowlist_denies_all(self) -> None:
        from src.auth import is_authorized

        settings = self._settings("")
        assert is_authorized("U111", settings) is False
