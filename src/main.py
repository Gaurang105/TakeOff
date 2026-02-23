"""Takeoff FastAPI application."""

import logging

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.slack_handler import handle_message_event, verify_slack_signature

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Takeoff", description="Slack bot that merges GitHub PRs on demand.")


@app.post("/slack/events")
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str = Header(default=""),
    x_slack_signature: str = Header(default=""),
) -> JSONResponse:
    """Receive and handle Slack event callbacks.

    Responds immediately with 200 OK (Slack requires < 3s).
    Heavy work (GitHub API call, Slack reply) runs in a background task.
    """
    body = await request.body()
    payload: dict[str, object] = {}
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    # Handle the one-time URL verification challenge before signature checks.
    # Slack sends this when first configuring the Events endpoint.
    if payload.get("type") == "url_verification":
        return JSONResponse({"challenge": payload.get("challenge")})

    settings = get_settings()

    if not verify_slack_signature(
        body=body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
        signing_secret=settings.slack_signing_secret,
    ):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")

    if payload.get("type") == "event_callback":
        event = payload.get("event")
        if isinstance(event, dict) and event.get("type") == "message":
            background_tasks.add_task(handle_message_event, event, settings)

    return JSONResponse({"ok": True})
