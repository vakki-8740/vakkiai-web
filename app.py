"""VakkiAI Web — Render-ready Flask application.

Production start:
    gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120

Local test:
    PORT=10000 python app.py
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    jsonify,
    request,
    send_file,
    send_from_directory,
)
from flask_cors import CORS

from backend.ai_client import AIClient, AIClientError
from backend.config import (
    DEFAULT_LANGUAGES,
    Settings,
    load_settings,
    redact_text,
)
from backend.safety import (
    ValidationError,
    validate_chat_payload,
    validate_note_payload,
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_ASSETS = {
    "styles.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "config.js": "application/javascript; charset=utf-8",
    "manifest.webmanifest": "application/manifest+json; charset=utf-8",
    "sw.js": "application/javascript; charset=utf-8",
    "icon.svg": "image/svg+xml",
}


class RateLimiter:
    """Simple in-memory per-IP limiter; free single-instance deployments ke liye."""

    def __init__(self, per_minute: int) -> None:
        self.per_minute = max(1, int(per_minute))
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                retry = max(1, math.ceil(60 - (now - hits[0])))
                return False, retry
            hits.append(now)
            return True, 0


def create_app(
    settings: Settings | None = None,
    ai_client: AIClient | None = None,
) -> Flask:
    settings = settings or load_settings()
    ai_client = ai_client or AIClient(settings)
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.config["JSON_SORT_KEYS"] = False
    app.extensions["vakkiai_settings"] = settings
    app.extensions["vakkiai_ai_client"] = ai_client
    app.extensions["vakkiai_rate_limiter"] = RateLimiter(
        settings.rate_limit_per_minute
    )

    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": list(settings.allowed_origins),
                "methods": ["GET", "POST", "OPTIONS"],
                "allow_headers": ["Content-Type"],
            }
        },
    )

    @app.after_request
    def security_headers(response: Any) -> Any:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Iframe preview aur normal browser dono kaam karein; isliye frame-ancestors
        # disable nahi kiya. API base alag host par ho sakta hai, isliye https allow.
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self' https:; object-src 'none'; "
            "base-uri 'self'",
        )
        if request.path.startswith("/api/") or request.path in {
            "/",
            "/health",
            "/config.js",
        }:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/")
    def index() -> Any:
        return send_from_directory(
            FRONTEND_DIR,
            "index.html",
            mimetype="text/html; charset=utf-8",
        )

    @app.get("/favicon.ico")
    def favicon() -> Any:
        return send_from_directory(
            FRONTEND_DIR,
            "icon.svg",
            mimetype="image/svg+xml",
        )

    @app.get("/<path:filename>")
    def frontend_asset(filename: str) -> Any:
        if filename not in STATIC_ASSETS:
            abort(404)
        return send_from_directory(
            FRONTEND_DIR,
            filename,
            mimetype=STATIC_ASSETS[filename],
        )

    @app.get("/health")
    def health() -> Any:
        return jsonify(
            {
                "status": "ok",
                "live_mode": True,
                "service": "vakkiai-web",
                "version": settings.version,
                "model": settings.model,
                "api_key_configured": settings.has_api_key,
                "voice": "Web Speech API — HTTPS + microphone + internet required",
                "notes": "browser localStorage + download; no server database",
                "port": os.environ.get("PORT", "10000"),
            }
        )

    @app.get("/api/config")
    def public_config() -> Any:
        return jsonify(
            {
                "app_name": settings.app_name,
                "model": settings.model,
                "has_api_key": settings.has_api_key,
                "default_language": settings.default_language,
                "languages": DEFAULT_LANGUAGES,
                "max_command_chars": settings.max_command_chars,
                "max_notes_chars": settings.max_notes_chars,
                "max_history_messages": settings.max_history_messages,
                "allowed_actions": ["none", "download_note"],
                "storage": "browser-local",
                "cors_origins": list(settings.allowed_origins),
            }
        )

    @app.errorhandler(404)
    def not_found(_error: Any) -> Any:
        if request.path.startswith("/api/"):
            return jsonify({"error": "API endpoint not found."}), 404
        return jsonify({"error": "Page not found."}), 404

    @app.errorhandler(413)
    def too_large(_error: Any) -> Any:
        return jsonify({"error": "Request body is too large."}), 413

    def _rate_limit() -> tuple[Any, int | None]:
        limiter = app.extensions["vakkiai_rate_limiter"]
        allowed, retry = limiter.allow(request.remote_addr or "unknown")
        if not allowed:
            response = jsonify(
                {"error": "Bahut saare requests bhej diye. Thodi der baad try karo."}
            )
            response.headers["Retry-After"] = str(retry or 1)
            return response, 429
        return None, None

    @app.post("/api/chat")
    def chat() -> Any:
        limited, status = _rate_limit()
        if limited is not None:
            return limited, status

        payload = request.get_json(silent=True)
        try:
            chat_request = validate_chat_payload(payload, settings)
        except ValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        if not settings.has_api_key:
            return jsonify(
                {
                    "error": "AI abhi configure nahi hai. Render Environment mein "
                    "OPENROUTER_API_KEY add karo."
                }
            ), 503
        try:
            reply = ai_client.ask(
                chat_request.command,
                chat_request.history,
                language=chat_request.language,
            )
        except AIClientError as exc:
            return jsonify(
                {"error": redact_text(str(exc), settings.api_key, limit=400)}
            ), 502
        except Exception:
            return jsonify({"error": "Unexpected server error. Please try again."}), 500
        return jsonify(reply.to_dict())

    @app.post("/api/note/download")
    def download_note() -> Any:
        limited, status = _rate_limit()
        if limited is not None:
            return limited, status
        payload = request.get_json(silent=True)
        try:
            note = validate_note_payload(payload, settings)
        except ValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        data = (note.text.rstrip() + "\n").encode("utf-8")
        response = send_file(
            BytesIO(data),
            mimetype="text/markdown",
            as_attachment=True,
            download_name=note.filename,
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


# Gunicorn expects module-level `app`.
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)
