"""OpenRouter client and safe response parser tests."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest
import requests

from backend.ai_client import AIClient, AIClientError, parse_ai_reply
from backend.config import Settings


class FakeResponse:
    def __init__(
        self,
        data: Any,
        *,
        status_code: int = 200,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._data = data
        self._json_error = json_error

    def json(self) -> Any:
        if self._json_error:
            raise self._json_error
        return self._data


class FakeSession:
    def __init__(
        self,
        response: FakeResponse | None = None,
        *,
        exception: Exception | None = None,
    ) -> None:
        self.response = response
        self.exception = exception
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.exception:
            raise self.exception
        if self.response is None:
            raise AssertionError("FakeSession needs a response")
        return self.response


def _chat_response(content: str) -> FakeResponse:
    return FakeResponse({"choices": [{"message": {"content": content}}]})


def test_missing_api_key_raises_without_network(settings: Settings) -> None:
    client = AIClient(replace(settings, api_key=""), session=FakeSession())
    with pytest.raises(AIClientError, match="OPENROUTER_API_KEY"):
        client.ask("hello")


def test_structured_response_and_payload(settings: Settings) -> None:
    payload = {
        "message": "Notes ready.",
        "notes": "# Admin Panel\n- Login",
        "suggested_filename": "admin_panel.md",
        "action": "download_note",
    }
    session = FakeSession(_chat_response(json.dumps(payload)))
    client = AIClient(settings, session=session)
    reply = client.ask(
        "Admin notes banao",
        [{"role": "user", "content": "Earlier"}],
        language="hi-IN",
    )
    assert reply.message == "Notes ready."
    assert reply.notes and "Admin Panel" in reply.notes
    assert reply.suggested_filename == "admin_panel.md"
    assert reply.action == "download_note"

    call = session.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {settings.api_key}"
    assert call["json"]["model"] == settings.model
    assert call["json"]["messages"][-1]["content"] == "Admin notes banao"
    assert "hi-IN" in call["json"]["messages"][0]["content"]
    assert call["timeout"] == (settings.connect_timeout, settings.read_timeout)


def test_plain_text_response_has_no_action(settings: Settings) -> None:
    client = AIClient(settings, session=FakeSession(_chat_response("Simple answer")))
    reply = client.ask("hello")
    assert reply.message == "Simple answer"
    assert reply.notes is None
    assert reply.action == "none"


def test_fenced_json_invalid_action_is_ignored(settings: Settings) -> None:
    raw = """```json
    {
      "message": "Unsafe request.",
      "notes": null,
      "suggested_filename": "safe.md",
      "action": "run_shell"
    }
    ```"""
    reply = parse_ai_reply(raw, settings)
    assert reply.action == "none"
    assert "Safe mode" in reply.message


def test_invalid_suggested_filename_falls_back(settings: Settings) -> None:
    raw = json.dumps(
        {
            "message": "Notes",
            "notes": "# Notes",
            "suggested_filename": "../unsafe.txt",
            "action": "download_note",
        }
    )
    reply = parse_ai_reply(raw, settings)
    assert reply.suggested_filename == "vakkiai-note.md"
    assert reply.action == "download_note"


def test_download_note_action_without_notes_becomes_none(settings: Settings) -> None:
    payload = {
        "message": "Okay",
        "notes": None,
        "suggested_filename": "notes.md",
        "action": "download_note",
    }
    reply = parse_ai_reply(json.dumps(payload), settings)
    assert reply.action == "none"
    assert reply.notes is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "API key invalid"),
        (402, "credit/plan"),
        (404, "Model ID"),
        (429, "rate limit"),
        (503, "server"),
    ],
)
def test_http_errors_are_friendly_and_redacted(
    settings: Settings, status: int, expected: str
) -> None:
    response = FakeResponse(
        {"error": {"message": f"bad key {settings.api_key}"}},
        status_code=status,
    )
    client = AIClient(settings, session=FakeSession(response))
    with pytest.raises(AIClientError) as exc_info:
        client.ask("hello")
    message = str(exc_info.value)
    assert expected in message
    assert settings.api_key not in message
    assert "[REDACTED]" in message


def test_timeout_and_connection_errors(settings: Settings) -> None:
    timeout_client = AIClient(
        settings, session=FakeSession(exception=requests.Timeout("slow"))
    )
    with pytest.raises(AIClientError, match="timed out"):
        timeout_client.ask("hello")

    connection_client = AIClient(
        settings, session=FakeSession(exception=requests.ConnectionError("offline"))
    )
    with pytest.raises(AIClientError, match="connect nahi"):
        connection_client.ask("hello")


def test_generic_request_error_never_leaks_key(settings: Settings) -> None:
    client = AIClient(
        settings,
        session=FakeSession(
            exception=requests.RequestException(f"failed {settings.api_key}")
        ),
    )
    with pytest.raises(AIClientError) as exc_info:
        client.ask("hello")
    assert settings.api_key not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse({"choices": []}),
        FakeResponse({"choices": [{"message": {"content": ""}}]}),
        FakeResponse({"unexpected": True}),
        FakeResponse(None, json_error=ValueError("not json")),
    ],
)
def test_invalid_api_responses(settings: Settings, response: FakeResponse) -> None:
    client = AIClient(settings, session=FakeSession(response))
    with pytest.raises(AIClientError):
        client.ask("hello")
