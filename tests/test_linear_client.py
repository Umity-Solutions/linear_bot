"""Unit tests for LinearClient."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from linear_client import LinearClient, LinearClientError, PRIORITY_MAP


FAKE_API_KEY = "lin_api_test"
FAKE_TEAM_ID = "team_123"


def _make_client():
    return LinearClient(api_key=FAKE_API_KEY, team_id=FAKE_TEAM_ID)


def _success_response(identifier="ENG-1", issue_id="abc", url="https://linear.app/issue/ENG-1"):
    return {
        "data": {
            "issueCreate": {
                "success": True,
                "issue": {"id": issue_id, "identifier": identifier, "url": url},
            }
        }
    }


class TestLinearClientInit:
    def test_sets_team_id(self):
        client = _make_client()
        assert client.team_id == FAKE_TEAM_ID

    def test_sets_auth_header(self):
        client = _make_client()
        assert client._session.headers["Authorization"] == FAKE_API_KEY


class TestCreateIssue:
    def test_returns_issue_on_success(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _success_response()
        mock_resp.raise_for_status.return_value = None

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            issue = client.create_issue("Fix bug", "Details here", "high")

        assert issue["identifier"] == "ENG-1"
        assert issue["url"] == "https://linear.app/issue/ENG-1"

        call_kwargs = mock_post.call_args
        sent_variables = call_kwargs.kwargs["json"]["variables"]
        assert sent_variables["title"] == "Fix bug"
        assert sent_variables["priority"] == PRIORITY_MAP["high"]

    def test_default_priority_is_medium(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _success_response()
        mock_resp.raise_for_status.return_value = None

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.create_issue("Some issue")

        sent_variables = mock_post.call_args.kwargs["json"]["variables"]
        assert sent_variables["priority"] == PRIORITY_MAP["medium"]

    def test_raises_on_api_errors(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"errors": [{"message": "Not authenticated"}]}
        mock_resp.raise_for_status.return_value = None

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(LinearClientError, match="Not authenticated"):
                client.create_issue("Title")

    def test_raises_when_success_false(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {"issueCreate": {"success": False, "issue": None}}
        }
        mock_resp.raise_for_status.return_value = None

        with patch.object(client._session, "post", return_value=mock_resp):
            with pytest.raises(LinearClientError, match="success=false"):
                client.create_issue("Title")

    def test_raises_on_http_error(self):
        client = _make_client()
        with patch.object(
            client._session,
            "post",
            side_effect=requests.RequestException("timeout"),
        ):
            with pytest.raises(LinearClientError, match="HTTP error"):
                client.create_issue("Title")

    @pytest.mark.parametrize(
        "priority_str,expected_num",
        [
            ("urgent", 1),
            ("high", 2),
            ("medium", 3),
            ("low", 4),
            ("no priority", 0),
            ("MEDIUM", 3),  # case-insensitive
            ("unknown", 3),  # unknown defaults to medium
        ],
    )
    def test_priority_mapping(self, priority_str, expected_num):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = _success_response()
        mock_resp.raise_for_status.return_value = None

        with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
            client.create_issue("Title", priority=priority_str)

        sent_variables = mock_post.call_args.kwargs["json"]["variables"]
        assert sent_variables["priority"] == expected_num
