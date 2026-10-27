"""Input validation and safe-note helpers for VakkiAI Web."""

from __future__ import annotations

import ntpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config import DEFAULT_LANGUAGES, Settings

CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
FILENAME_RE = re.compile(r"[A-Za-z0-9._-]+")
LANGUAGE_RE = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?")
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
ALLOWED_ACTIONS = frozenset({"none", "download_note"})


class ValidationError(ValueError):
    """User/AI input unsafe ya invalid hone par."""


@dataclass(frozen=True)
class ChatRequest:
    command: str
    history: list[dict[str, str]]
    language: str


@dataclass(frozen=True)
class NoteDownload:
    filename: str
    text: str


def sanitize_text(
    value: Any,
    *,
    max_chars: int,
    required: bool = True,
    field_name: str = "text",
) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string.")
    if CONTROL_CHAR_RE.search(value):
        raise ValidationError(f"{field_name} contains unsupported control characters.")
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if required and not text:
        raise ValidationError(f"{field_name} cannot be empty.")
    if len(text) > max_chars:
        raise ValidationError(
            f"{field_name} is too long (limit: {max_chars} characters)."
        )
    return text


def validate_filename(
    value: Any,
    *,
    default: str = "vakkiai-note.md",
    strict: bool = True,
) -> str:
    """Sirf simple .md/.txt basename allow karo.

    ``strict=False`` AI suggestion ke liye hai: invalid name par safe default milta hai.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if strict:
            raise ValidationError("Filename is required.")
        return default
    if not isinstance(value, str):
        if strict:
            raise ValidationError("Filename must be text.")
        return default

    name = value.strip()
    too_long = len(name) > 100
    invalid_chars = not FILENAME_RE.fullmatch(name)
    path_like = Path(name).name != name or ntpath.basename(name) != name
    hidden_or_dot = name.startswith(".") or name.endswith((".", " ")) or ".." in name
    path = Path(name)
    bad_suffix = path.suffix.lower() not in {".md", ".txt"}
    reserved = not path.stem or path.stem.upper() in WINDOWS_RESERVED_NAMES

    if too_long or invalid_chars or path_like or hidden_or_dot or bad_suffix or reserved:
        if strict:
            raise ValidationError(
                "Use a simple .md or .txt filename (letters, numbers, dot, dash, underscore)."
            )
        return default
    return name


def validate_language(value: Any, *, default: str = "hi-IN") -> str:
    if isinstance(value, str) and LANGUAGE_RE.fullmatch(value.strip()):
        return value.strip()
    if value in DEFAULT_LANGUAGES.values():
        return str(value)
    return default


def validate_history(value: Any, settings: Settings) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValidationError("history must be a list.")

    cleaned: list[dict[str, str]] = []
    max_chars = min(settings.max_response_chars, 4000)
    for item in value:
        if not isinstance(item, Mapping):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = content.strip()
        if not content or CONTROL_CHAR_RE.search(content):
            continue
        cleaned.append({"role": role, "content": content[:max_chars]})
    return cleaned[-settings.max_history_messages :]


def validate_chat_payload(payload: Any, settings: Settings) -> ChatRequest:
    if not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.")
    command = sanitize_text(
        payload.get("command"),
        max_chars=settings.max_command_chars,
        required=True,
        field_name="command",
    )
    history = validate_history(payload.get("history", []), settings)
    language = validate_language(payload.get("language"), default=settings.default_language)
    return ChatRequest(command=command, history=history, language=language)


def validate_note_payload(payload: Any, settings: Settings) -> NoteDownload:
    if not isinstance(payload, Mapping):
        raise ValidationError("Request body must be a JSON object.")
    filename = validate_filename(payload.get("filename"), strict=True)
    text = sanitize_text(
        payload.get("text"),
        max_chars=settings.max_notes_chars,
        required=True,
        field_name="text",
    )
    return NoteDownload(filename=filename, text=text)


def safe_action(value: Any) -> tuple[str, str]:
    """AI action allowlist. Return (action, warning)."""
    if value in ALLOWED_ACTIONS:
        return str(value), ""
    return "none", (
        "\n\n[Safe mode] AI ne unsupported action request bheja; usse ignore "
        "kar diya gaya."
    )
