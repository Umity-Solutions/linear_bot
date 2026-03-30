"""Linear GraphQL API — create issues with the invoking user's API key."""

from __future__ import annotations

import json
from typing import Any

import requests

LINEAR_GRAPHQL = "https://api.linear.app/graphql"

ISSUE_CREATE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
"""


def create_issue(
    linear_api_key: str,
    team_id: str,
    title: str,
    description: str,
    project_id: str | None = None,
) -> str:
    """
    Create a Linear issue. Returns the issue URL.
    Raises RuntimeError on GraphQL errors or missing URL.
    """
    input_payload: dict[str, Any] = {
        "teamId": team_id,
        "title": title,
        "description": description,
    }
    if project_id:
        input_payload["projectId"] = project_id

    body = {
        "query": ISSUE_CREATE_MUTATION,
        "variables": {"input": input_payload},
    }
    r = requests.post(
        LINEAR_GRAPHQL,
        headers={
            "Authorization": linear_api_key,
            "Content-Type": "application/json",
        },
        data=json.dumps(body),
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data and data["errors"]:
        msgs = "; ".join(
            e.get("message", str(e)) for e in data["errors"]
        )
        raise RuntimeError(f"Linear GraphQL: {msgs}")

    payload = data.get("data") or {}
    ic = payload.get("issueCreate") or {}
    if not ic.get("success"):
        raise RuntimeError("Linear issueCreate was not successful (check team ID, key, and permissions)")

    issue = ic.get("issue") or {}
    url = issue.get("url")
    if not url:
        ident = issue.get("identifier", "?")
        raise RuntimeError(f"Linear issue created but no URL (identifier: {ident})")
    return url
