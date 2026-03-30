# linear_bot — Slack `/ticket` → Linear

Workspace Slack app: run `/ticket` in a channel or thread to create a **Linear issue** using **your** Linear API key (stored in a central **secret** GitHub Gist). Thread messages are pasted into the issue body once at creation (no live sync).

## Stack

- Python 3.11+, Flask, gunicorn
- `slack-sdk` (signature verification + `conversations.replies`)
- Anthropic Claude for issue title + Markdown body
- Linear GraphQL (`issueCreate`) with per-user personal API keys
- One GitHub Gist file `ticket_users.json` + **in-memory cache** (no per-request Gist GET)

## Why gunicorn `--workers 1`

Each worker keeps its own in-memory copy of `ticket_users.json`. Multiple workers can disagree until restart. For this internal tool, run **a single worker** (see `Dockerfile` and `railway.toml`). If you scale workers later, add a periodic Gist refresh or another shared store.

## Setup

### 1. GitHub Gist

1. Create a **secret** gist (plaintext API keys must not be in a public gist).
2. Add a file named **`ticket_users.json`** with content: `{}`
3. Note the gist ID from the URL: `https://gist.github.com/<user>/<GIST_ID>`
4. Create a [GitHub PAT](https://github.com/settings/tokens) with **`gist`** scope (`GITHUB_TOKEN`).

### 2. Linear

- Each user needs a **personal API key** (Linear → Settings → API).
- **Team ID** is a UUID (open the team in Linear, or use the API / GraphQL). Optional **project ID** UUID for default project.

### 3. Slack app

1. Create a Slack app; **Install to workspace**.
2. **Slash command** `/ticket` → Request URL `https://<your-host>/ticket` (POST).
3. **OAuth & Permissions** — bot token scopes:
   - `channels:history`, `groups:history`
   - `channels:read`, `groups:read`
   - `users:read`
   - `commands`
4. **Install** again after scope changes; copy **Bot User OAuth Token** and **Signing Secret**.
5. **Invite the bot** to channels where `/ticket` should read threads (`/invite @YourBot`).

### 4. Environment

Copy [`.env.example`](.env.example) to `.env` and fill values. Never commit secrets.

| Variable | Purpose |
|----------|---------|
| `SLACK_BOT_TOKEN` | `xoxb-...` |
| `SLACK_SIGNING_SECRET` | Signing secret |
| `ANTHROPIC_API_KEY` | Claude |
| `GITHUB_TOKEN` | PAT with `gist` |
| `GITHUB_GIST_ID` | Central gist id |
| `PORT` | Listen port (local / platform) |
| `ANTHROPIC_MODEL` | Optional model override |

### 5. Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' .env | xargs)
gunicorn app:app --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120
```

### 6. Deploy

- **Docker**: build from [`Dockerfile`](Dockerfile); set `PORT` if the platform injects it.
- **Railway**: [`railway.toml`](railway.toml) runs gunicorn with `$PORT` and `/health` checks.

## Usage

- **Register** (only you see the reply):  
  `/ticket register <linear_api_key> <default_team_id>`  
  Optional: `/ticket register <key> <team_id> <default_project_id>`

- **Create issue**: `/ticket` plus notes. Inside a **thread**, the thread transcript is included under a **Slack thread** section in the Linear description.

## API routes

| Method | Path | Role |
|--------|------|------|
| POST | `/ticket` | Slack slash command |
| GET | `/health` | Load balancer / platform health |

## Repository layout

- [`app.py`](app.py) — Flask routes, Claude, async worker + `response_url`
- [`gist_store.py`](gist_store.py) — Gist GET/PATCH, in-memory map, lock + retry
- [`linear_client.py`](linear_client.py) — Linear `issueCreate`
- [`slack_helpers.py`](slack_helpers.py) — Slack verify, thread fetch, Markdown transcript

## License

See [LICENSE](LICENSE).
