"""Linear API client for creating and managing tickets."""

import requests


LINEAR_API_URL = "https://api.linear.app/graphql"

PRIORITY_MAP = {
    "urgent": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "no priority": 0,
}


class LinearClientError(Exception):
    """Raised when the Linear API returns an error."""


class LinearClient:
    """Thin wrapper around the Linear GraphQL API."""

    def __init__(self, api_key: str, team_id: str) -> None:
        self.team_id = team_id
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": api_key,
                "Content-Type": "application/json",
            }
        )

    def create_issue(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
    ) -> dict:
        """Create a Linear issue and return its id, identifier and url.

        Args:
            title: Issue title.
            description: Issue body in markdown.
            priority: One of 'urgent', 'high', 'medium', 'low', 'no priority'.

        Returns:
            A dict with keys ``id``, ``identifier``, and ``url``.

        Raises:
            LinearClientError: If the API returns errors or the request fails.
        """
        priority_num = PRIORITY_MAP.get(priority.lower(), PRIORITY_MAP["medium"])

        mutation = """
        mutation CreateIssue($teamId: String!, $title: String!, $description: String, $priority: Int) {
            issueCreate(input: {
                teamId: $teamId,
                title: $title,
                description: $description,
                priority: $priority
            }) {
                success
                issue {
                    id
                    identifier
                    url
                }
            }
        }
        """
        variables = {
            "teamId": self.team_id,
            "title": title,
            "description": description,
            "priority": priority_num,
        }

        try:
            response = self._session.post(
                LINEAR_API_URL,
                json={"query": mutation, "variables": variables},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise LinearClientError(f"HTTP error communicating with Linear: {exc}") from exc

        data = response.json()
        if errors := data.get("errors"):
            messages = "; ".join(e.get("message", str(e)) for e in errors)
            raise LinearClientError(f"Linear API error: {messages}")

        issue_create = data.get("data", {}).get("issueCreate", {})
        if not issue_create.get("success"):
            raise LinearClientError("Linear issueCreate returned success=false")

        return issue_create["issue"]
