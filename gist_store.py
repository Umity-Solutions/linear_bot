"""
Central GitHub Gist JSON storage for Slack user → Linear credentials.
In-memory cache with write-through PATCH; threading lock for register races.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import requests

GIST_FILENAME = "ticket_users.json"
GITHUB_API = "https://api.github.com"
MAX_PATCH_RETRIES = 5

_store_lock = threading.Lock()
_users: dict[str, dict[str, Any]] | None = None
_loaded = False


def _headers() -> dict[str, str]:
    token = os.environ["GITHUB_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _gist_id() -> str:
    return os.environ["GITHUB_GIST_ID"]


def ensure_loaded() -> None:
    """GET gist once per process; populate in-memory map."""
    global _users, _loaded
    if _loaded:
        return
    with _store_lock:
        if _loaded:
            return
        gist_id = _gist_id()
        r = requests.get(f"{GITHUB_API}/gists/{gist_id}", headers=_headers(), timeout=60)
        r.raise_for_status()
        files = r.json().get("files") or {}
        f = files.get(GIST_FILENAME) or {}
        raw = f.get("content") or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        _users = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        _loaded = True


def get_user(slack_user_id: str) -> dict[str, Any] | None:
    ensure_loaded()
    assert _users is not None
    u = _users.get(slack_user_id)
    return dict(u) if u else None


def _patch_gist_file(new_content: str) -> None:
    gist_id = _gist_id()
    r = requests.patch(
        f"{GITHUB_API}/gists/{gist_id}",
        headers=_headers(),
        json={"files": {GIST_FILENAME: {"content": new_content}}},
        timeout=60,
    )
    r.raise_for_status()


def upsert_user(
    slack_user_id: str,
    linear_api_key: str,
    default_team_id: str,
    default_project_id: str | None,
) -> None:
    """
    Read-modify-write gist with retries: re-fetch and merge on failure.
    Updates module-level _users on success (write-through).
    """
    ensure_loaded()
    assert _users is not None

    record = {
        "linear_api_key": linear_api_key,
        "default_team_id": default_team_id,
        "default_project_id": default_project_id,
    }

    with _store_lock:
        for attempt in range(MAX_PATCH_RETRIES):
            try:
                gist_id = _gist_id()
                gr = requests.get(f"{GITHUB_API}/gists/{gist_id}", headers=_headers(), timeout=60)
                gr.raise_for_status()
                files = gr.json().get("files") or {}
                f = files.get(GIST_FILENAME) or {}
                raw = f.get("content") or "{}"
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                data = {str(k): v for k, v in data.items() if isinstance(v, dict)}
                data[slack_user_id] = record
                new_content = json.dumps(data, indent=2, sort_keys=True) + "\n"
                _patch_gist_file(new_content)
                _users.update(data)
                return
            except (requests.RequestException, OSError) as e:
                if attempt == MAX_PATCH_RETRIES - 1:
                    raise RuntimeError(f"Gist upsert failed after {MAX_PATCH_RETRIES} attempts: {e}") from e
                time.sleep(0.3 * (2**attempt))
