"""Validation, config and redaction tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from backend.config import ConfigError, Settings, load_settings, redact_text
from backend.safety import (
    ValidationError,
    safe_action,
    sanitize_text,
    validate_chat_payload,
    validate_filename,
    validate_history,
    validate_language,
    validate_note_payload,
)


def test_load_settings_from_explicit_environment(tmp_path: Path) -> None:
    env = {
        "OPENROUTER_API_KEY": "  test-key-value  ",
        "OPENROUTER_MODEL": "openai/gpt-4o-mini",
        "VAKKIAI_DEFAULT_LANGUAGE": "en-IN",
        "VAKKIAI_ALLOWED_ORIGINS": "https://a.example, https://b.example",
        "VAKKIAI_RATE_LIMIT_PER_MINUTE": "30",
    }
    settings = load_settings(env, base_dir=tmp_path)
    assert settings.api_key == "test-key-value"
    assert settings.default_language == "en-IN"
    assert settings.allowed_origins == ("https://a.example", "https://b.example")
    assert settings.rate_limit_per_minute == 30
    assert "test-key-value" not in repr(settings)


def test_invalid_model_and_url_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="model"):
        load_settings({"OPENROUTER_MODEL": "bad model!"}, base_dir=tmp_path)
    with pytest.raises(ConfigError, match="HTTPS"):
        load_settings(
            {"OPENROUTER_API_URL": "http://example.invalid/api"}, base_dir=tmp_path
        )


def test_redact_text_replaces_secret() -> None:
    result = redact_text("failed with token abcdefghijk", "abcdefghijk")
    assert "abcdefghijk" not in result
    assert "[REDACTED]" in result


@pytest.mark.parametrize(
    "bad_name",
    [
        "../secret.md",
        r"C:\Windows\secret.md",
        "notes/secret.md",
        "..",
        ".hidden.md",
        "secret.exe",
        "CON.md",
        "secret name.md",
        "secret.md\x00",
        "",
    ],
)
def test_unsafe_note_filenames_are_rejected(bad_name: str) -> None:
    with pytest.raises(ValidationError):
        validate_filename(bad_name)


def test_valid_note_filenames() -> None:
    assert validate_filename("admin_panel.md") == "admin_panel.md"
    assert validate_filename("  requirements.txt  ") == "requirements.txt"


def test_ai_suggested_filename_uses_safe_default() -> None:
    assert validate_filename("../bad.md", strict=False) == "vakkiai-note.md"
    assert validate_filename(None, strict=False) == "vakkiai-note.md"


def test_sanitize_text_rejects_control_characters() -> None:
    assert sanitize_text("  hello\nworld  ", max_chars=100) == "hello\nworld"
    with pytest.raises(ValidationError, match="control"):
        sanitize_text("hello\x1b[2J", max_chars=100)
    with pytest.raises(ValidationError, match="empty"):
        sanitize_text("   ", max_chars=100)


def test_validate_history_trims_and_filters(settings: Settings) -> None:
    history = [
        {"role": "user", "content": f"q{i}"} for i in range(10)
    ] + [
        {"role": "assistant", "content": f"a{i}"} for i in range(10)
    ]
    history.insert(0, {"role": "system", "content": "ignore"})
    history.insert(1, {"role": "user", "content": "bad\x1b"})
    cleaned = validate_history(history, settings)
    assert len(cleaned) == settings.max_history_messages
    assert all(item["role"] in {"user", "assistant"} for item in cleaned)


def test_validate_chat_payload(settings: Settings) -> None:
    request = validate_chat_payload(
        {
            "command": "  hello  ",
            "history": [{"role": "user", "content": "old"}],
            "language": "en-US",
        },
        settings,
    )
    assert request.command == "hello"
    assert request.language == "en-US"
    assert request.history == [{"role": "user", "content": "old"}]

    with pytest.raises(ValidationError):
        validate_chat_payload({"command": "x" * 1000}, settings)


def test_validate_note_payload(settings: Settings) -> None:
    note = validate_note_payload(
        {"filename": "notes.md", "text": "  # Notes  "}, settings
    )
    assert note.filename == "notes.md"
    assert note.text == "# Notes"
    with pytest.raises(ValidationError):
        validate_note_payload({"filename": "../x.md", "text": "hello"}, settings)


def test_validate_language_fallback() -> None:
    assert validate_language("hi-IN") == "hi-IN"
    assert validate_language("bad code") == "hi-IN"
    assert validate_language(None, default="en-IN") == "en-IN"


def test_safe_action_allowlist() -> None:
    assert safe_action("none") == ("none", "")
    assert safe_action("download_note") == ("download_note", "")
    action, warning = safe_action("run_shell")
    assert action == "none"
    assert "Safe mode" in warning
