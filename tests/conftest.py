"""Shared pytest fixtures for VakkiAI Web."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.ai_client import AIClientError, AIReply  # noqa: E402
from backend.config import Settings  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="sk-test-SECRET-1234567890",
        model="test/model",
        api_url="https://openrouter.ai/api/v1/chat/completions",
        connect_timeout=0.2,
        read_timeout=0.5,
        max_command_chars=500,
        max_response_chars=5000,
        max_notes_chars=2000,
        max_history_messages=4,
        default_language="hi-IN",
        allowed_origins=("*",),
        rate_limit_per_minute=20,
    )


class FakeAI:
    def __init__(
        self,
        reply: AIReply | None = None,
        error: Exception | None = None,
    ) -> None:
        self.reply = reply or AIReply(
            message="Test AI reply",
            notes="# Test Notes\n- Item",
            suggested_filename="test_notes.md",
            action="download_note",
        )
        self.error = error
        self.calls: list[dict[str, object]] = []

    def ask(self, command: str, history=None, *, language: str = "hi-IN") -> AIReply:
        self.calls.append(
            {"command": command, "history": list(history or []), "language": language}
        )
        if self.error:
            raise self.error
        return self.reply


@pytest.fixture
def fake_ai() -> FakeAI:
    return FakeAI()


@pytest.fixture
def client(settings: Settings, fake_ai: FakeAI):
    from app import create_app

    app = create_app(settings=settings, ai_client=fake_ai)
    app.testing = True
    return app.test_client(), app, fake_ai, settings


@pytest.fixture
def no_key_settings(settings: Settings) -> Settings:
    return replace(settings, api_key="")
