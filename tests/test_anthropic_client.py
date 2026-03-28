"""Unit tests for AnthropicClient."""

import json
from unittest.mock import MagicMock, patch

import pytest

import anthropic as anthropic_module
from anthropic_client import AnthropicClient, AnthropicClientError


FAKE_API_KEY = "sk-ant-test"


def _make_client(model="claude-3-5-haiku-20241022"):
    return AnthropicClient(api_key=FAKE_API_KEY, model=model)


def _mock_message(text: str):
    """Build a mock Anthropic Message object whose content[0].text == text."""
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


class TestAnthropicClientInit:
    def test_stores_model(self):
        client = _make_client(model="claude-3-opus-20240229")
        assert client.model == "claude-3-opus-20240229"


class TestExtractTicketInfo:
    def test_returns_parsed_json(self):
        client = _make_client()
        payload = {
            "title": "Fix login bug",
            "description": "Users cannot log in on Safari.",
            "priority": "high",
        }
        with patch.object(client._client.messages, "create", return_value=_mock_message(json.dumps(payload))):
            result = client.extract_ticket_info("Fix the login bug ASAP")

        assert result["title"] == "Fix login bug"
        assert result["priority"] == "high"

    def test_strips_markdown_fences(self):
        client = _make_client()
        payload = {"title": "T", "description": "D", "priority": "low"}
        wrapped = f"```json\n{json.dumps(payload)}\n```"
        with patch.object(client._client.messages, "create", return_value=_mock_message(wrapped)):
            result = client.extract_ticket_info("something")

        assert result["title"] == "T"

    def test_raises_on_invalid_json(self):
        client = _make_client()
        with patch.object(client._client.messages, "create", return_value=_mock_message("not json")):
            with pytest.raises(AnthropicClientError, match="Could not parse"):
                client.extract_ticket_info("anything")

    def test_raises_when_key_missing(self):
        client = _make_client()
        incomplete = json.dumps({"title": "T", "description": "D"})  # missing priority
        with patch.object(client._client.messages, "create", return_value=_mock_message(incomplete)):
            with pytest.raises(AnthropicClientError, match="Missing key 'priority'"):
                client.extract_ticket_info("anything")

    def test_raises_on_api_error(self):
        client = _make_client()
        with patch.object(
            client._client.messages,
            "create",
            side_effect=anthropic_module.APIStatusError(
                "bad request",
                response=MagicMock(status_code=400),
                body={},
            ),
        ):
            with pytest.raises(AnthropicClientError, match="Anthropic API error"):
                client.extract_ticket_info("anything")
