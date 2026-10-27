"""Flask API tests — no real network, no real files."""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.ai_client import AIClientError


def test_index_serves_mobile_frontend(client) -> None:
    test_client, _app, _ai, _settings = client
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"VakkiAI" in response.data
    assert b"manifest.webmanifest" in response.data
    assert "Content-Security-Policy" in response.headers


def test_static_assets_and_unknown_path(client) -> None:
    test_client, _app, _ai, _settings = client
    assert test_client.get("/styles.css").status_code == 200
    assert test_client.get("/app.js").status_code == 200
    assert test_client.get("/config.js").status_code == 200
    assert test_client.get("/manifest.webmanifest").status_code == 200
    assert test_client.get("/icon.svg").status_code == 200
    assert test_client.get("/sw.js").status_code == 200
    assert test_client.get("/favicon.ico").status_code == 200
    assert test_client.get("/not-here").status_code == 404
    assert test_client.get("/api/not-here").status_code == 404


def test_health_and_config_never_expose_key(client) -> None:
    test_client, _app, _ai, settings = client
    health = test_client.get("/health")
    assert health.status_code == 200
    assert health.get_json()["status"] == "ok"
    assert health.get_json()["live_mode"] is True
    assert health.get_json()["api_key_configured"] is True
    assert settings.api_key not in health.get_data(as_text=True)

    config = test_client.get("/api/config")
    assert config.status_code == 200
    payload = config.get_json()
    assert payload["has_api_key"] is True
    assert payload["default_language"] == "hi-IN"
    assert payload["allowed_actions"] == ["none", "download_note"]
    assert settings.api_key not in config.get_data(as_text=True)


def test_chat_success_calls_backend_with_validated_payload(client) -> None:
    test_client, _app, ai, settings = client
    response = test_client.post(
        "/api/chat",
        json={
            "command": "Admin Panel notes banao",
            "history": [
                {"role": "user", "content": "Old question"},
                {"role": "assistant", "content": "Old answer"},
            ],
            "language": "hi-IN",
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["message"] == "Test AI reply"
    assert data["notes"].startswith("# Test Notes")
    assert data["suggested_filename"] == "test_notes.md"
    assert data["action"] == "download_note"
    assert ai.calls[0]["command"] == "Admin Panel notes banao"
    assert ai.calls[0]["language"] == "hi-IN"
    assert len(ai.calls[0]["history"]) == 2
    assert settings.api_key not in response.get_data(as_text=True)


def test_chat_missing_key_returns_503(no_key_settings, fake_ai) -> None:
    from app import create_app

    app = create_app(settings=no_key_settings, ai_client=fake_ai)
    app.testing = True
    response = app.test_client().post("/api/chat", json={"command": "hello"})
    assert response.status_code == 503
    assert "OPENROUTER_API_KEY" in response.get_json()["error"]
    assert fake_ai.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"command": ""},
        {"command": "hello", "history": "bad"},
        {"command": "hello\x1b[2J"},
    ],
)
def test_chat_invalid_payloads_return_400(client, payload) -> None:
    test_client, _app, _ai, _settings = client
    response = test_client.post("/api/chat", json=payload)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_chat_ai_error_is_redacted(client) -> None:
    test_client, _app, ai, settings = client
    ai.error = AIClientError(f"OpenRouter rejected {settings.api_key}")
    response = test_client.post("/api/chat", json={"command": "hello"})
    assert response.status_code == 502
    body = response.get_data(as_text=True)
    assert settings.api_key not in body
    assert "[REDACTED]" in body


def test_note_download_returns_safe_file(client) -> None:
    test_client, _app, _ai, _settings = client
    response = test_client.post(
        "/api/note/download",
        json={"filename": "admin_panel.md", "text": "# Admin\n- Login"},
    )
    assert response.status_code == 200
    assert "attachment" in response.headers["Content-Disposition"]
    assert "admin_panel.md" in response.headers["Content-Disposition"]
    assert response.data.decode("utf-8") == "# Admin\n- Login\n"


@pytest.mark.parametrize(
    "payload",
    [
        {"filename": "../evil.md", "text": "hello"},
        {"filename": "evil.exe", "text": "hello"},
        {"filename": "notes/evil.md", "text": "hello"},
        {"filename": "good.md", "text": ""},
        {"filename": "good.md", "text": "bad\x1b[2J"},
    ],
)
def test_note_download_rejects_unsafe_payload(client, payload) -> None:
    test_client, _app, _ai, _settings = client
    response = test_client.post("/api/note/download", json=payload)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_rate_limit_blocks_excess_requests(settings, fake_ai) -> None:
    from app import create_app

    limited = replace(settings, rate_limit_per_minute=2)
    app = create_app(settings=limited, ai_client=fake_ai)
    app.testing = True
    test_client = app.test_client()
    assert test_client.post("/api/chat", json={"command": "one"}).status_code == 200
    assert test_client.post("/api/chat", json={"command": "two"}).status_code == 200
    third = test_client.post("/api/chat", json={"command": "three"})
    assert third.status_code == 429
    assert third.headers["Retry-After"].isdigit()


def test_cors_headers_present_for_api(client) -> None:
    test_client, _app, _ai, _settings = client
    response = test_client.get(
        "/api/config",
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" in response.headers


def test_request_body_limit(client) -> None:
    test_client, _app, _ai, _settings = client
    response = test_client.post(
        "/api/chat",
        data=b"x" * (70 * 1024),
        content_type="application/json",
    )
    assert response.status_code == 413
