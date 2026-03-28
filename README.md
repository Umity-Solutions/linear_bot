# linear_bot

A Slack bot that creates [Linear](https://linear.app) tickets from natural language using [Anthropic](https://anthropic.com) Claude.

## How it works

1. A user invokes the bot via a slash command or an app mention in Slack.
2. The bot sends the message to Claude, which extracts a structured ticket (title, description, priority).
3. The bot creates the ticket in Linear via the GraphQL API and posts the link back to Slack.

## Supported interactions

| Interaction | Example |
|---|---|
| Slash command | `/linear-ticket The login page crashes on Safari – fix ASAP` |
| App mention | `@linear-bot Add dark mode to the settings screen` |

## Setup

### Prerequisites

- Python 3.12+
- A [Slack app](https://api.slack.com/apps) with:
  - **Bot Token Scopes**: `app_mentions:read`, `chat:write`, `commands`
  - A `/linear-ticket` slash command configured
  - Socket Mode enabled (for local development)
- An [Anthropic API key](https://console.anthropic.com/)
- A [Linear API key](https://linear.app/settings/api) and your team ID

### Install dependencies

```bash
pip install -r requirements.txt
```

### Configure environment variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-…`) |
| `SLACK_SIGNING_SECRET` | Signing secret for request verification |
| `SLACK_APP_TOKEN` | App-level token for Socket Mode (`xapp-…`) |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `LINEAR_API_KEY` | Linear personal API key (`lin_api_…`) |
| `LINEAR_TEAM_ID` | ID of the Linear team to create issues in |

### Run the bot

```bash
python app.py
```

## Running tests

```bash
pip install pytest
python -m pytest tests/ -v
```
