"""Anthropic client that extracts structured ticket information from free-form text."""

import json
import re

import anthropic


SYSTEM_PROMPT = """\
You are an assistant that extracts structured information for a Linear ticket from a user's message.

Return ONLY a valid JSON object (no markdown fences, no extra text) with these keys:
- "title": a concise ticket title (string, max 80 characters)
- "description": a detailed description in markdown (string)
- "priority": one of "urgent", "high", "medium", "low", or "no priority" (string)

Choose priority based on cues in the message (e.g. "ASAP", "critical" → urgent; "when possible", "nice to have" → low).
Default to "medium" when no clear cue is present.
"""


class AnthropicClientError(Exception):
    """Raised when ticket extraction fails."""


class AnthropicClient:
    """Wrapper around the Anthropic Messages API for ticket extraction."""

    def __init__(self, api_key: str, model: str = "claude-3-5-haiku-20241022") -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def extract_ticket_info(self, user_message: str) -> dict:
        """Extract title, description and priority from *user_message*.

        Args:
            user_message: The raw text written by the Slack user.

        Returns:
            A dict with keys ``title``, ``description``, and ``priority``.

        Raises:
            AnthropicClientError: If the API call fails or the response cannot
                be parsed as the expected JSON structure.
        """
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
        except anthropic.APIError as exc:
            raise AnthropicClientError(f"Anthropic API error: {exc}") from exc

        raw = message.content[0].text.strip()

        # Strip optional markdown code fences in case the model wraps the JSON
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            ticket_info = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AnthropicClientError(
                f"Could not parse Anthropic response as JSON: {exc}\nRaw response: {raw}"
            ) from exc

        for key in ("title", "description", "priority"):
            if key not in ticket_info:
                raise AnthropicClientError(f"Missing key '{key}' in Anthropic response")

        return ticket_info
