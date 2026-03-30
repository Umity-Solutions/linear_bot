#!/usr/bin/env python3
"""
Slack /ticket bot — create Linear issues from a channel or thread using per-user Linear API keys stored in a GitHub Gist.
"""

from __future__ import annotations

import json
import os
import re
import threading
import traceback
from typing import Any

import anthropic
import requests
from flask import Flask, jsonify, request
from slack_sdk import WebClient

import gist_store
import linear_client
import slack_helpers

app = Flask(__name__)

USAGE = (
    "*`/ticket`* — Create a Linear issue from your note (and thread, if you run it inside a thread).\n\n"
    "*`/ticket register`* — Save your Linear credentials (visible only to you).\n"
    "`/ticket register <linear_api_key> <default_team_id>`\n"
    "Optional: `/ticket register <key> <team_id> <default_project_id>`\n\n"
    "Get your API key from Linear → Settings → API. Team ID is a UUID from the team URL or GraphQL."
)

DEFAULT_MODEL = "claude-sonnet-4-20250514"


def get_slack_client() -> WebClient:
    return WebClient(token=os.environ["SLACK_BOT_TOKEN"])


def get_anthropic() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)


def _reply_url(response_url: str, text: str, ephemeral: bool = True) -> None:
    payload: dict[str, Any] = {"text": text}
    if ephemeral:
        payload["response_type"] = "ephemeral"
    try:
        requests.post(response_url, json=payload, timeout=30)
    except Exception as e:
        print(f"[ticket-bot] response_url post failed: {e}")


def _parse_ticket_json(raw: str) -> tuple[str, str]:
    """Extract title and description from Claude output (JSON preferred)."""
    raw = raw.strip()
    m = re.search(r"\{[\s\S]*\}\s*$", raw)
    if m:
        try:
            obj = json.loads(m.group(0))
            t = (obj.get("title") or "").strip()
            d = (obj.get("description") or "").strip()
            if t and d:
                return t, d
        except json.JSONDecodeError:
            pass
    lines = raw.split("\n", 1)
    title = lines[0].strip("# ").strip()[:500] if lines else "Ticket"
    body = lines[1].strip() if len(lines) > 1 else raw
    return title, body


def generate_issue_content(
    client: anthropic.Anthropic,
    user_note: str,
    thread_markdown: str | None,
    channel_name: str,
    extra_context: str,
) -> tuple[str, str]:
    """Claude returns JSON: title + description (Markdown) with Slack thread section when relevant."""
    parts = [
        "You format content for a Linear issue (Markdown).",
        "Respond with ONLY a JSON object, no markdown fences, in this exact shape:",
        '{"title": "<short imperative title>", "description": "<full body markdown>"}',
        "",
        f"Channel: #{channel_name}",
        extra_context,
        "",
        "User note / intent:",
        user_note or "(none)",
    ]
    if thread_markdown:
        parts.extend(
            [
                "",
                "Include in `description` a section titled exactly `## Slack thread` followed by the transcript below (preserve meaning).",
                "Transcript:",
                thread_markdown,
            ]
        )

    prompt = "\n".join(parts)

    resp = client.messages.create(
        model=_model(),
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = (resp.content[0].text or "").strip()
    return _parse_ticket_json(text)


def process_ticket_async(
    channel_id: str,
    thread_ts: str | None,
    user_id: str,
    text: str,
    response_url: str,
) -> None:
    slack = get_slack_client()

    def reply(msg: str) -> None:
        _reply_url(response_url, msg, ephemeral=True)

    try:
        user = gist_store.get_user(user_id)
        if not user:
            reply(
                "You are not registered yet. Run:\n"
                "`/ticket register <linear_api_key> <default_team_id>`\n"
                "(Only you will see this message.)"
            )
            return

        key = user.get("linear_api_key")
        team = user.get("default_team_id")
        if not key or not team:
            reply("Your saved Linear settings are incomplete. Run `/ticket register` again.")
            return

        project = user.get("default_project_id")
        project_id = project if project else None

        channel_name = slack_helpers.get_channel_name(slack, channel_id)
        thread_md: str | None = None
        extra = ""

        if thread_ts:
            messages = slack_helpers.fetch_thread_messages(slack, channel_id, thread_ts)
            thread_md = slack_helpers.format_thread_markdown(slack, messages)
            pl = slack_helpers.get_permalink(slack, channel_id, thread_ts)
            if pl:
                extra = f"Thread permalink: {pl}"
        else:
            extra = f"Command run from channel #{channel_name} (not inside a thread)."

        client = get_anthropic()
        title, description = generate_issue_content(
            client,
            text.strip(),
            thread_md,
            channel_name,
            extra,
        )

        url = linear_client.create_issue(
            str(key),
            str(team),
            title,
            description,
            project_id=str(project_id) if project_id else None,
        )

        reply(f"Created Linear issue: {url}")
    except Exception as e:
        print(f"[ticket-bot] Error: {e}")
        print(traceback.format_exc())
        reply(f"Something went wrong: {e}")


def parse_register(text: str) -> tuple[str, str, str | None] | None:
    """If text starts with 'register', return (api_key, team_id, project_id|None)."""
    parts = text.strip().split()
    if len(parts) < 3:
        return None
    if parts[0].lower() != "register":
        return None
    api_key = parts[1]
    team_id = parts[2]
    project_id: str | None = parts[3] if len(parts) > 3 else None
    return api_key, team_id, project_id


@app.route("/ticket", methods=["POST"])
def handle_ticket():
    body = request.get_data()
    if not slack_helpers.verify_request(body, request.headers):
        print("[ticket-bot] Signature verification failed")
        return jsonify({"error": "Forbidden"}), 403

    payload = request.form.to_dict()
    response_url = payload.get("response_url", "")
    text = (payload.get("text") or "").strip()
    channel_id = payload.get("channel_id", "")
    user_id = payload.get("user_id", "")
    thread_ts = payload.get("thread_ts") or None

    if text.lower().startswith("register"):
        reg = parse_register(text)
        if reg is None:
            return jsonify(
                {
                    "response_type": "ephemeral",
                    "text": (
                        "Usage: `/ticket register <linear_api_key> <default_team_id>`\n"
                        "Optional project: `/ticket register <key> <team_id> <project_id>`"
                    ),
                }
            )
        api_key, team_id, project_id = reg
        try:
            gist_store.upsert_user(user_id, api_key, team_id, project_id)
        except Exception as e:
            print(traceback.format_exc())
            return jsonify(
                {
                    "response_type": "ephemeral",
                    "text": f"Could not save settings: {e}",
                }
            )
        return jsonify(
            {
                "response_type": "ephemeral",
                "text": "Saved your Linear API key and default team for `/ticket`.",
            }
        )

    if not text:
        return jsonify({"response_type": "ephemeral", "text": USAGE})

    t = threading.Thread(
        target=process_ticket_async,
        args=(channel_id, thread_ts, user_id, text, response_url),
    )
    t.daemon = True
    t.start()

    return jsonify(
        {
            "response_type": "ephemeral",
            "text": "Creating Linear issue…",
        }
    )


@app.route("/health", methods=["GET"])
def health():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"[ticket-bot] Starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
