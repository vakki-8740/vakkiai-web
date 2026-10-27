"""Configuration for VakkiAI Web (live hosting mode)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_LANGUAGES = {
    "Hindi (India)": "hi-IN",
    "English (India)": "en-IN",
    "English (US)": "en-US",
}

SYSTEM_PROMPT = """You are VakkiAI Web, a safe AI assistant running in a mobile browser.
Reply in the same language/style as the user (Hindi, Hinglish, or English).

Return ONLY one valid JSON object:
{
  "message": "short conversational reply",
  "notes": "optional well-formatted Markdown notes, or null",
  "suggested_filename": "simple_name.md",
  "action": "none"
}

Rules:
- "action" may ONLY be "none" or "download_note".
- Use "download_note" only when the user explicitly asks to prepare/save/download notes.
- "suggested_filename" must be a simple ASCII .md or .txt basename: letters, numbers, dot, dash, underscore only. No folders or paths.
- Never request shell commands, PowerShell, Python code, SQL, HTTP requests, or any desktop automation.
- Never include executable code or instruct the app to evaluate text.
- Never claim that a file was saved; the browser asks the user and downloads it locally.
- Keep notes useful and structured with headings and bullet points.
- Do not wrap JSON in Markdown fences.
"""


class ConfigError(ValueError):
    """Configuration value galat hone par readable error."""


@dataclass(frozen=True)
class Settings:
    """Runtime settings. API key repr() aur logs se chhupayi gayi hai."""

    api_key: str = field(default="", repr=False)
    model: str = DEFAULT_MODEL
    api_url: str = DEFAULT_API_URL
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    max_command_chars: int = 4000
    max_response_chars: int = 16000
    max_notes_chars: int = 12000
    max_history_messages: int = 8
    default_language: str = "hi-IN"
    allowed_origins: tuple[str, ...] = ("*",)
    rate_limit_per_minute: int = 20
    app_name: str = "VakkiAI Web"
    version: str = "1.0.0"

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key.strip())


def _optional_load_dotenv(dotenv_path: Path) -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    load_dotenv(dotenv_path=dotenv_path, override=False)


def _get_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number.") from exc
    if not 1 <= value <= 300:
        raise ConfigError(f"{name} must be between 1 and 300 seconds.")
    return value


def _get_int(
    env: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number.") from exc
    if not minimum <= value <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _validate_model(model: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._:/@+-]{3,120}", model):
        raise ConfigError("OPENROUTER_MODEL has unsupported characters in the model ID.")
    return model


def _validate_api_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError("OPENROUTER_API_URL must be a valid HTTPS URL.")
    return url


def _validate_language(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?", value):
        raise ConfigError("VAKKIAI_DEFAULT_LANGUAGE must look like hi-IN or en-US.")
    return value


def _parse_origins(raw: str) -> tuple[str, ...]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values or "*" in values:
        return ("*",)
    return tuple(dict.fromkeys(values))


def load_settings(
    env: Mapping[str, str] | None = None,
    *,
    base_dir: Path = BASE_DIR,
) -> Settings:
    if env is None:
        _optional_load_dotenv(base_dir / ".env")
        env = os.environ

    return Settings(
        api_key=env.get("OPENROUTER_API_KEY", "").strip(),
        model=_validate_model(env.get("OPENROUTER_MODEL", "").strip() or DEFAULT_MODEL),
        api_url=_validate_api_url(
            env.get("OPENROUTER_API_URL", "").strip() or DEFAULT_API_URL
        ),
        connect_timeout=_get_float(env, "VAKKIAI_CONNECT_TIMEOUT", 10.0),
        read_timeout=_get_float(env, "VAKKIAI_READ_TIMEOUT", 60.0),
        max_command_chars=_get_int(
            env, "VAKKIAI_MAX_COMMAND_CHARS", 4000, minimum=100, maximum=16000
        ),
        max_response_chars=_get_int(
            env, "VAKKIAI_MAX_RESPONSE_CHARS", 16000, minimum=500, maximum=64000
        ),
        max_notes_chars=_get_int(
            env, "VAKKIAI_MAX_NOTES_CHARS", 12000, minimum=500, maximum=64000
        ),
        max_history_messages=_get_int(
            env, "VAKKIAI_MAX_HISTORY_MESSAGES", 8, minimum=1, maximum=30
        ),
        default_language=_validate_language(
            env.get("VAKKIAI_DEFAULT_LANGUAGE", "hi-IN").strip() or "hi-IN"
        ),
        allowed_origins=_parse_origins(
            env.get("VAKKIAI_ALLOWED_ORIGINS", "*")
        ),
        rate_limit_per_minute=_get_int(
            env, "VAKKIAI_RATE_LIMIT_PER_MINUTE", 20, minimum=1, maximum=120
        ),
    )


def redact_text(value: object, *secrets: str, limit: int = 600) -> str:
    """Error messages se API key aur lambi bodies hatao."""
    text = str(value)
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "[REDACTED]")
    text = text.replace("\r", " ").replace("\n", " ")
    return text[:limit]
