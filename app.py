"""Slack bot that creates Linear tickets from natural language using Anthropic AI.

Supported interactions
----------------------
* **Slash command** ``/linear-ticket <text>``
* **App mention**   ``@BotName <text>``

Environment variables (see .env.example)
-----------------------------------------
SLACK_BOT_TOKEN       – Bot User OAuth Token (xoxb-…)
SLACK_SIGNING_SECRET  – Signing secret for request verification
SLACK_APP_TOKEN       – App-level token for Socket Mode (xapp-…)
ANTHROPIC_API_KEY     – Anthropic API key
LINEAR_API_KEY        – Linear personal API key (lin_api_…)
LINEAR_TEAM_ID        – ID of the Linear team to create issues in
"""

import logging
import os

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from anthropic_client import AnthropicClient, AnthropicClientError
from linear_client import LinearClient, LinearClientError

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slack app initialisation
# ---------------------------------------------------------------------------

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
)

# ---------------------------------------------------------------------------
# Shared service clients (lazy-initialised so tests can patch them easily)
# ---------------------------------------------------------------------------

_anthropic_client: AnthropicClient | None = None
_linear_client: LinearClient | None = None


def get_anthropic_client() -> AnthropicClient:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = AnthropicClient(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _anthropic_client


def get_linear_client() -> LinearClient:
    global _linear_client
    if _linear_client is None:
        _linear_client = LinearClient(
            api_key=os.environ["LINEAR_API_KEY"],
            team_id=os.environ["LINEAR_TEAM_ID"],
        )
    return _linear_client


# ---------------------------------------------------------------------------
# Core ticket-creation helper
# ---------------------------------------------------------------------------

def create_ticket_from_text(text: str) -> str:
    """Parse *text* with Anthropic, create a Linear ticket, return Slack message.

    Args:
        text: Raw user message describing the desired ticket.

    Returns:
        A Slack-formatted response string.
    """
    try:
        ticket_info = get_anthropic_client().extract_ticket_info(text)
    except AnthropicClientError as exc:
        logger.error("Anthropic error: %s", exc)
        return f":x: Could not extract ticket information: {exc}"

    try:
        issue = get_linear_client().create_issue(
            title=ticket_info["title"],
            description=ticket_info.get("description", ""),
            priority=ticket_info.get("priority", "medium"),
        )
    except LinearClientError as exc:
        logger.error("Linear error: %s", exc)
        return f":x: Could not create Linear ticket: {exc}"

    return (
        f":white_check_mark: Linear ticket created!\n"
        f"*{issue['identifier']}* – {ticket_info['title']}\n"
        f"Priority: *{ticket_info.get('priority', 'medium').capitalize()}*\n"
        f"{issue['url']}"
    )


# ---------------------------------------------------------------------------
# Slack event/action handlers
# ---------------------------------------------------------------------------

@app.command("/linear-ticket")
def handle_slash_command(ack, respond, command):
    """Handle /linear-ticket <description> slash command."""
    ack()
    text = (command.get("text") or "").strip()
    if not text:
        respond(":warning: Please provide a ticket description. Usage: `/linear-ticket <description>`")
        return
    respond(create_ticket_from_text(text))


@app.event("app_mention")
def handle_app_mention(event, say):
    """Handle @BotName <description> mentions."""
    # Strip the bot mention (e.g. "<@U12345> ") from the beginning
    raw_text = event.get("text", "")
    # Remove leading mention token(s) like <@UXXXXXX>
    text = raw_text.split(">", 1)[-1].strip() if ">" in raw_text else raw_text.strip()
    if not text:
        say(":warning: Please describe the ticket after mentioning me.")
        return
    say(create_ticket_from_text(text))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    logger.info("Starting Linear Bot in Socket Mode…")
    handler.start()
