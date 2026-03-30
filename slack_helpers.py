"""Slack signature verification, thread fetch with cap, transcript Markdown."""

from __future__ import annotations

import os
import re
from typing import Any

from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier

MAX_THREAD_MESSAGES = 100


def get_signing_secret() -> str:
    return os.environ["SLACK_SIGNING_SECRET"]


def verify_request(body: bytes, headers) -> bool:
    verifier = SignatureVerifier(get_signing_secret())
    return verifier.is_valid_request(body, headers)


def fetch_thread_messages(
    slack: WebClient,
    channel_id: str,
    thread_ts: str,
    max_messages: int = MAX_THREAD_MESSAGES,
) -> list[dict[str, Any]]:
    """Paginate conversations.replies until max_messages or end."""
    out: list[dict[str, Any]] = []
    cursor: str | None = None
    while len(out) < max_messages:
        limit = min(200, max_messages - len(out))
        kwargs: dict[str, Any] = {
            "channel": channel_id,
            "ts": thread_ts,
            "limit": limit,
        }
        if cursor:
            kwargs["cursor"] = cursor
        result = slack.conversations_replies(**kwargs)
        messages = result.get("messages") or []
        out.extend(messages)
        has_more = result.get("has_more")
        meta = result.get("response_metadata") or {}
        next_c = meta.get("next_cursor")
        if not has_more or not next_c:
            break
        cursor = next_c
        if len(messages) == 0:
            break
    return out[:max_messages]


def _display_name(slack: WebClient, user_id: str, cache: dict[str, str]) -> str:
    if user_id in cache:
        return cache[user_id]
    try:
        info = slack.users_info(user=user_id)
        u = (info.get("user") or {}) if info else {}
        prof = u.get("profile") or {}
        name = (
            prof.get("display_name")
            or prof.get("real_name")
            or u.get("name")
            or user_id
        )
        cache[user_id] = name or user_id
    except Exception:
        cache[user_id] = user_id
    return cache[user_id]


def _strip_slack_tokens(text: str) -> str:
    """Remove <@U...> mention wrappers; keep user-readable fragments where possible."""
    t = re.sub(r"<@([A-Z0-9]+)>", r"@\1", text)
    t = re.sub(r"<#([A-Z0-9]+)\|([^>]+)>", r"#\2", t)
    t = re.sub(r"<#([A-Z0-9]+)>", r"#channel", t)
    t = re.sub(r"<([^|>]+)\|([^>]+)>", r"\2", t)
    t = re.sub(r"<(https?://[^>]+)>", r"\1", t)
    return t


def format_thread_markdown(
    slack: WebClient,
    messages: list[dict[str, Any]],
) -> str:
    """User names + text, chronological, as Markdown lines."""
    cache: dict[str, str] = {}
    lines: list[str] = []
    for msg in messages:
        uid = msg.get("user") or ""
        text = (msg.get("text") or "").strip()
        if text.startswith("/ticket"):
            continue
        if not text:
            continue
        text = _strip_slack_tokens(text)
        if uid:
            who = _display_name(slack, uid, cache)
            lines.append(f"**{who}:** {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def get_channel_name(slack: WebClient, channel_id: str) -> str:
    try:
        info = slack.conversations_info(channel=channel_id)
        return (info.get("channel") or {}).get("name") or channel_id
    except Exception:
        return channel_id


def get_permalink(slack: WebClient, channel_id: str, message_ts: str) -> str | None:
    try:
        r = slack.chat_getPermalink(channel=channel_id, message_ts=message_ts)
        return r.get("permalink")
    except Exception:
        return None
