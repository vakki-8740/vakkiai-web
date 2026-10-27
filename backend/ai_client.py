"""OpenRouter client for VakkiAI Web."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import requests

from backend.config import SYSTEM_PROMPT, Settings, redact_text
from backend.safety import (
    ValidationError,
    safe_action,
    sanitize_text,
    validate_filename,
)


class AIClientError(RuntimeError):
    """User-friendly AI/API error."""


@dataclass(frozen=True)
class AIReply:
    message: str
    notes: str | None
    suggested_filename: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "notes": self.notes,
            "suggested_filename": self.suggested_filename,
            "action": self.action,
        }


def _json_candidate(raw: str) -> str | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
        if candidate[:4].lower() == "json":
            candidate = candidate[4:].lstrip()
        return candidate if candidate.startswith("{") else None

    start = text.find("{")
    if start < 0:
        return None
    try:
        _, end = json.JSONDecoder().raw_decode(text[start:])
        return text[start : start + end]
    except json.JSONDecodeError:
        end = text.rfind("}")
        return text[start : end + 1] if end > start else None


def _plain_reply(raw: str, settings: Settings) -> AIReply:
    try:
        message = sanitize_text(
            raw,
            max_chars=settings.max_response_chars,
            required=True,
            field_name="AI response",
        )
    except ValidationError as exc:
        raise AIClientError(f"AI response was not usable: {exc}") from exc
    return AIReply(
        message=message,
        notes=None,
        suggested_filename="vakkiai-note.md",
        action="none",
    )


def _safe_sanitize(
    value: Any,
    *,
    max_chars: int,
    field_name: str,
) -> str | None:
    try:
        return sanitize_text(
            value,
            max_chars=max_chars,
            required=False,
            field_name=field_name,
        )
    except ValidationError:
        return None


def parse_ai_reply(raw: str, settings: Settings) -> AIReply:
    """Structured JSON parse karo; failure par plain text par safely fallback karo."""
    if not isinstance(raw, str) or not raw.strip():
        raise AIClientError("OpenRouter returned an empty response.")
    if len(raw) > settings.max_response_chars:
        raw = raw[: settings.max_response_chars]

    candidate = _json_candidate(raw)
    if candidate is None:
        return _plain_reply(raw, settings)
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _plain_reply(raw, settings)
    if not isinstance(data, Mapping):
        return _plain_reply(raw, settings)

    message = _safe_sanitize(
        data.get("message"),
        max_chars=settings.max_response_chars,
        field_name="message",
    )
    if not message:
        return _plain_reply(raw, settings)

    notes = None
    if isinstance(data.get("notes"), str) and data["notes"].strip():
        notes = _safe_sanitize(
            data["notes"],
            max_chars=settings.max_notes_chars,
            field_name="notes",
        )

    action, warning = safe_action(data.get("action", "none"))
    if action == "download_note" and not notes:
        action = "none"
    suggested_filename = validate_filename(
        data.get("suggested_filename"),
        default="vakkiai-note.md",
        strict=False,
    )
    return AIReply(
        message=message + warning,
        notes=notes or None,
        suggested_filename=suggested_filename,
        action=action,
    )


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, Mapping):
        return _content_to_text(content.get("text", ""))
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


class AIClient:
    """OpenRouter chat-completions client with timeout and sanitized errors."""

    def __init__(self, settings: Settings, session: Any | None = None) -> None:
        self.settings = settings
        self.session = session or requests.Session()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
            "X-Title": "VakkiAI Web",
        }

    def _error_detail(self, response: Any) -> str:
        try:
            data = response.json()
        except Exception:
            return ""
        message = ""
        if isinstance(data, Mapping):
            error = data.get("error")
            if isinstance(error, Mapping) and isinstance(error.get("message"), str):
                message = error["message"]
            elif isinstance(error, str):
                message = error
            elif isinstance(data.get("message"), str):
                message = data["message"]
        return redact_text(message, self.settings.api_key, limit=300)

    def _http_error(self, response: Any) -> AIClientError:
        status = getattr(response, "status_code", None)
        detail = self._error_detail(response)
        if status == 401:
            message = "OpenRouter API key invalid ya missing hai. Render environment check karo."
        elif status == 402:
            message = "OpenRouter account mein credit/plan issue hai."
        elif status == 404:
            message = "Model ID ya API endpoint galat hai. OPENROUTER_MODEL check karo."
        elif status == 429:
            message = "OpenRouter rate limit reach ho gaya. Thodi der baad try karo."
        elif isinstance(status, int) and status >= 500:
            message = "OpenRouter server abhi available nahi hai. Thodi der baad try karo."
        else:
            message = f"OpenRouter HTTP error ({status})."
        if detail:
            message += f" Detail: {detail}"
        return AIClientError(message)

    def ask(
        self,
        command: str,
        history: Sequence[Mapping[str, str]] | None = None,
        *,
        language: str = "hi-IN",
    ) -> AIReply:
        if not self.settings.has_api_key:
            raise AIClientError(
                "OPENROUTER_API_KEY set nahi hai. Render service ke Environment "
                "settings mein key add karo."
            )
        system = (
            SYSTEM_PROMPT
            + f"\nPreferred reply language code: {language}. Match the user's actual language."
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for item in history or []:
            if not isinstance(item, Mapping):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in {"user", "assistant"} and isinstance(content, str):
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": command})

        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 1500,
        }
        try:
            response = self.session.post(
                self.settings.api_url,
                headers=self._headers(),
                json=payload,
                timeout=(self.settings.connect_timeout, self.settings.read_timeout),
            )
        except requests.Timeout as exc:
            raise AIClientError(
                "OpenRouter request timed out. Internet ya timeout settings check karo."
            ) from exc
        except requests.ConnectionError as exc:
            raise AIClientError(
                "OpenRouter se connect nahi ho paya. Internet connection check karo."
            ) from exc
        except requests.RequestException as exc:
            raise AIClientError(
                redact_text(
                    f"Network request failed: {exc}",
                    self.settings.api_key,
                    limit=300,
                )
            ) from exc

        status = getattr(response, "status_code", None)
        if not isinstance(status, int) or not 200 <= status < 300:
            raise self._http_error(response)
        try:
            data = response.json()
        except (ValueError, TypeError) as exc:
            raise AIClientError("OpenRouter returned invalid JSON.") from exc
        if not isinstance(data, Mapping):
            raise AIClientError("OpenRouter response shape invalid hai.")
        choices = data.get("choices")
        if not isinstance(choices, Sequence) or not choices:
            raise AIClientError("OpenRouter response mein koi choice nahi mili.")
        first = choices[0]
        if not isinstance(first, Mapping) or not isinstance(first.get("message"), Mapping):
            raise AIClientError("OpenRouter response mein valid message nahi mila.")
        raw = _content_to_text(first["message"].get("content"))
        return parse_ai_reply(raw, self.settings)
