# Takeoff

A stateless Slack bot that merges GitHub PRs on demand. Mention a PR URL in Slack with merge intent and Takeoff handles the rest.

## How It Works

1. A teammate posts a GitHub PR link in Slack with words like "merge", "please merge", or "@takeoff can u"
2. Takeoff verifies the sender is authorized
3. Takeoff merges the PR via the GitHub API
4. Takeoff replies in the Slack thread confirming the merge

## Setup

### 1. Clone and create virtual environment

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create a Slack App

- Go to https://api.slack.com/apps and create a new app
- Under **OAuth & Permissions**, add these bot token scopes:
  - `chat:write`
  - `channels:history`
  - `groups:history`
  - `im:history`
- Under **Event Subscriptions**, enable events and set the Request URL to:
  `https://<your-host>/slack/events`
- Subscribe to bot events: `message.channels`, `message.groups`, `message.im`
- Install the app to your workspace and copy the **Bot User OAuth Token**
- Copy the **Signing Secret** from Basic Information

### 3. Create a GitHub Token

- Go to https://github.com/settings/tokens
- Create a fine-grained PAT with **Read and Write** access to **Pull Requests** and **Contents** for the relevant repositories

### 4. Configure environment variables

```bash
cp .env.example .env
# Fill in SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, GITHUB_TOKEN, AUTHORIZED_SLACK_USER_IDS
```

`AUTHORIZED_SLACK_USER_IDS` is a comma-separated list of Slack user IDs (e.g. `U012AB3CD,U056EF7GH`) allowed to trigger merges. Find a user's ID by clicking their profile in Slack → More → Copy member ID.

### 5. Run

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

For production, expose the server via a reverse proxy (nginx, Caddy) or deploy to Railway/Fly.io.

## Development

```bash
pip install -r requirements-dev.txt

# Format
black src/ tests/
isort src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/

# Tests
pytest
```

## Trigger Examples

The bot activates on any message that contains a GitHub PR URL **and** a merge-intent keyword:

- "Please merge this - https://github.com/org/repo/pull/42"
- "@takeoff can u https://github.com/org/repo/pull/42"
- "merge https://github.com/org/repo/pull/42 when available"

## Error Handling

| Situation | Bot Response |
|---|---|
| User not authorized | "Sorry, you're not authorized to trigger merges." |
| PR already merged | "PR #N is already merged." |
| Merge conflicts | "Cannot merge PR #N - there are conflicts." |
| CI checks pending/failing | "Cannot merge PR #N - status checks have not passed." |
| GitHub API error | "Failed to merge PR #N: `<reason>`" |
