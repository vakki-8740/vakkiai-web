"""Deployment, frontend and safety static checks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_render_yaml_is_live_ready_and_secret_safe() -> None:
    yaml = _read("render.yaml")
    assert "type: web" in yaml
    assert "runtime: python" in yaml
    assert "healthCheckPath: /health" in yaml
    assert "gunicorn app:app" in yaml
    assert "0.0.0.0:$PORT" in yaml
    assert "OPENROUTER_API_KEY" in yaml
    assert "sync: false" in yaml
    assert "sk-or-" not in yaml


def test_procfile_and_python_version() -> None:
    procfile = _read("Procfile")
    assert "gunicorn app:app" in procfile
    assert "0.0.0.0:$PORT" in procfile
    assert _read(".python-version").strip() == "3.12"


def test_requirements_are_web_only() -> None:
    # Comments me desktop package names ho sakte hain; sirf actual requirement lines check karo.
    lines = [
        line.strip().lower()
        for line in _read("requirements.txt").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    requirements = "\n".join(lines)
    assert "flask" in requirements
    assert "flask-cors" in requirements
    assert "gunicorn" in requirements
    assert "requests" in requirements
    for desktop_only in ["tkinter", "pyaudio", "pyautogui", "pyperclip", "speechrecognition"]:
        assert desktop_only not in requirements


def test_frontend_files_exist_and_are_self_contained() -> None:
    for name in [
        "index.html",
        "styles.css",
        "app.js",
        "config.js",
        "manifest.webmanifest",
        "sw.js",
        "icon.svg",
    ]:
        assert (ROOT / "frontend" / name).is_file()

    html = _read("frontend/index.html")
    assert "src=\"./app.js\"" in html
    assert "src=\"./config.js\"" in html
    # Placeholder URLs allowed hain; external scripts/stylesheets allowed nahi.
    assert "<script src=\"http://" not in html
    assert "<script src=\"https://" not in html
    assert "<link rel=\"stylesheet\" href=\"http://" not in html
    assert "<link rel=\"stylesheet\" href=\"https://" not in html

    app_js = _read("frontend/app.js")
    assert "innerHTML" not in app_js
    assert "eval(" not in app_js
    assert "document.write" not in app_js
    assert "/api/chat" in app_js
    assert "SpeechRecognition" in app_js

    config_js = _read("frontend/config.js")
    assert "window.VAKKIAI_API_BASE = \"\"" in config_js

    sw = _read("frontend/sw.js")
    assert "\"/api/\"" in sw
    assert "request.method !== \"GET\"" in sw


def test_backend_has_no_desktop_only_imports() -> None:
    python_files = [ROOT / "app.py"] + list((ROOT / "backend").glob("*.py"))
    text = "\n".join(path.read_text(encoding="utf-8") for path in python_files)
    for desktop_only in [
        "import tkinter",
        "import pyautogui",
        "import pyperclip",
        "import pyaudio",
        "import speech_recognition",
        "notepad.exe",
        "shell=True",
        "eval(",
        "exec(",
    ]:
        assert desktop_only not in text


def test_app_binds_to_render_port_in_local_fallback() -> None:
    app_py = _read("app.py")
    assert "0.0.0.0" in app_py
    assert "PORT" in app_py
    assert "app = create_app()" in app_py
    assert "/health" in app_py


def test_readme_explains_live_tablet_mode() -> None:
    readme = _read("README.md")
    assert "Render" in readme
    assert "Android tablet" in readme
    assert "OPENROUTER_API_KEY" in readme
    assert "Web Speech API" in readme
    assert "DEPLOY-RENDER.md" in readme
