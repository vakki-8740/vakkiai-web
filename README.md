# VakkiAI Web — Live / Render Edition

Ye **Android tablet / mobile browser** ke liye bana hua live web version hai. Isme **Windows, Tkinter, Notepad, PyAudio ya PyAutoGUI ki zarurat nahi**. Aap Chrome me HTTPS URL khol kar text ya voice se AI assistant use kar sakte ho.

> Ye `VakkiAI.zip` wale Windows desktop project ka replacement hai, usi ka upgraded web avatar. Desktop zip ab bhi reference ke liye hai, par live hosting ke liye **yahin wala project** use karo.

---

## 1. Architecture

```text
Android tablet / Chrome
        │
        ▼
Frontend: HTML + CSS + JavaScript
  - text input
  - Start/Stop voice (Web Speech API)
  - chat UI
  - localStorage notes + .md download
  - PWA installable
        │  HTTPS JSON
        ▼
Backend: Flask on Render
  - /api/chat
  - /api/note/download
  - /api/config
  - /health
  - input validation + rate limit + CORS
        │
        ▼
OpenRouter API (server-side API key)
```

**Frontend aur backend alag folders me hain:**

```text
frontend/   → browser UI (static files)
backend/    → Python business logic
app.py      → Flask web server / entry point
```

Agar chahein to dono ko **ek hi Render service** par host kar sakte ho. Ya frontend ko kisi static host par aur backend ko Render par alag host kar sakte ho — dono supported hain.

---

## 2. Kya kya hai / nahi hai

| Item | Status |
|---|---|
| Windows desktop GUI | ❌ Nahi |
| Android tablet browser UI | ✅ Haan |
| Text command | ✅ Haan |
| Voice command | ✅ Browser Web Speech API se |
| OpenRouter AI | ✅ Server-side |
| API key browser me | ❌ Kabhi nahi |
| Notes save | ✅ Tablet localStorage + `.md` download |
| Server database | ❌ Nahi (privacy + free tier ke liye) |
| Notepad automation | ❌ Nahi (web version me zarurat nahi) |
| Docker | ❌ Zarurat nahi; Render Python runtime use karta hai |
| Render Blueprint | ✅ `render.yaml` included |
| Health check | ✅ `/health` |
| CORS for split hosting | ✅ Haan |

---

## 3. Technology stack

**Frontend**

- HTML5
- CSS3, mobile-first, dark-mode aware
- Vanilla JavaScript — koi React/Angular/build step nahi
- Web Speech API (`SpeechRecognition` / `webkitSpeechRecognition`)
- Service worker + `manifest.webmanifest` for PWA

**Backend**

- Python 3.12
- Flask
- Flask-CORS
- Requests
- python-dotenv
- Gunicorn
- OpenRouter Chat Completions API

**Hosting**

- Render Web Service
- `PORT` environment variable
- Bind on `0.0.0.0:$PORT`
- Secret in Render Environment, not in Git

Render ke liye `0.0.0.0` aur `$PORT` par bind karna zaroori hai; official docs: <https://render.com/docs/web-services> aur <https://render.com/docs/deploy-flask>.

---

## 4. Quick deploy — ek hi Render service (recommended)

Detailed tablet steps: [`DEPLOY-RENDER.md`](./DEPLOY-RENDER.md).

Short version:

1. Is project ko GitHub repo me daalo.
2. Render Dashboard → **New → Blueprint** → repo select karo.
3. `render.yaml` automatically read hoga.
4. Render prompt par apni **OpenRouter API key** daalo.
5. Deploy complete hone par URL milega, jaise:
   ```text
   https://vakkiai-web.onrender.com
   ```
6. Tablet ke Chrome me URL kholo → mic allow karo → use karo.

> **Important:** `OPENROUTER_API_KEY` kabhi `config.js`, HTML ya frontend me mat daalo. Sirf Render ke Environment variables me daalo. `render.yaml` me `sync: false` isliye hai ki secret Git me na aaye. Reference: <https://render.com/docs/blueprint-spec>.

---

## 5. Manual Render settings (agar Blueprint use na karein)

| Setting | Value |
|---|---|
| Language / Runtime | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120` |
| Health Check Path | `/health` |
| Instance Type | Free (testing) ya Starter (production) |

Environment variables:

| Variable | Required | Example |
|---|---:|---|
| `OPENROUTER_API_KEY` | ✅ | Render Dashboard me set karo |
| `OPENROUTER_MODEL` | ✅ | `openai/gpt-4o-mini` |
| `OPENROUTER_API_URL` | optional | `https://openrouter.ai/api/v1/chat/completions` |
| `VAKKIAI_DEFAULT_LANGUAGE` | optional | `hi-IN` |
| `VAKKIAI_ALLOWED_ORIGINS` | optional | `*` ya `https://your-frontend.netlify.app` |
| `VAKKIAI_RATE_LIMIT_PER_MINUTE` | optional | `20` |
| `VAKKIAI_CONNECT_TIMEOUT` | optional | `10` |
| `VAKKIAI_READ_TIMEOUT` | optional | `60` |
| `VAKKIAI_MAX_COMMAND_CHARS` | optional | `4000` |
| `VAKKIAI_MAX_NOTES_CHARS` | optional | `12000` |
| `VAKKIAI_MAX_HISTORY_MESSAGES` | optional | `8` |
| `PYTHON_VERSION` | optional | `3.12` |

---

## 6. API endpoints

| Method | Path | Kaam |
|---|---|---|
| `GET` | `/` | Mobile frontend |
| `GET` | `/health` | Render health check; safe diagnostics |
| `GET` | `/api/config` | Public config — model, languages, limits; **key nahi** |
| `POST` | `/api/chat` | Command + history → AI response |
| `POST` | `/api/note/download` | Validated text ko `.md/.txt` file banakar download |

### `POST /api/chat` request

```json
{
  "command": "Admin Panel ke features ki notes banao",
  "history": [
    {"role": "user", "content": "Earlier question"},
    {"role": "assistant", "content": "Earlier answer"}
  ],
  "language": "hi-IN"
}
```

### `POST /api/chat` response

```json
{
  "message": "Notes ready.",
  "notes": "# Admin Panel\n- Login\n- Users",
  "suggested_filename": "admin_panel_notes.md",
  "action": "download_note"
}
```

Sirf 2 actions allow hain: `none` aur `download_note`. Koi shell, Python code ya arbitrary command execute nahi hota.

---

## 7. Notes ka system

- AI response me `notes` aaye to **Notes** card dikhta hai.
- **Save on tablet** → browser `localStorage` me save.
- **Download .md** → file tablet ke Downloads folder me.
- Saved notes list se dobara download ya delete kar sakte ho.
- Server par notes permanently store nahi hote.

**Reason:** Render free web service ka local filesystem restart ke baad permanent nahi hota. Isliye user data ko browser/device par rakhna zyada safe aur simple hai. Agar chahiye to aage chalkar Render Postgres ya Supabase add kar sakte hain.

---

## 8. Voice input on Android tablet

Voice browser ke **Web Speech API** se chalta hai.

Requirements:

- HTTPS URL — Render automatically HTTPS deta hai.
- Chrome ya Edge recommended.
- Microphone permission allow karo.
- Internet chahiye, kyunki Chrome aksar audio ko cloud recognition service ko bhejta hai.
- Firefox / kuch embedded webviews me support nahi hota; text input fallback hai.

References:

- MDN SpeechRecognition: <https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition>
- MDN Web Speech API: <https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API>
- Browser support notes: <https://www.assemblyai.com/blog/speech-recognition-javascript-web-speech-api>

---

## 9. Frontend aur backend alag host karna

Agar aap frontend ko Netlify / GitHub Pages / Cloudflare Pages par aur backend ko Render par rakhna chahte ho:

1. `frontend/` folder ko static host par upload karo.
2. Backend Render service ka URL lo, jaise `https://vakkiai-api.onrender.com`.
3. Do options:
   - `frontend/config.js` me set karo:
     ```js
     window.VAKKIAI_API_BASE = "https://vakkiai-api.onrender.com";
     ```
   - Ya app ke **Backend settings** card me URL daal kar **Save URL** dabao.
4. Render backend me set karo:
   ```dotenv
   VAKKIAI_ALLOWED_ORIGINS=https://your-frontend.netlify.app
   ```
   Multiple origins comma-separated de sakte ho.

> API key hamesha backend par hi rahegi. Frontend sirf Render backend ko call karega.

---

## 10. Local test (sirf developer ke liye)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest -q
PORT=10000 python app.py
```

Phir browser me:

```text
http://localhost:10000
http://localhost:10000/health
```

Production me `python app.py` use mat karo; Render `gunicorn` use karega.

---

## 11. Security

- API key sirf server environment se.
- `/api/config` aur `/health` kabhi key print nahi karte.
- Request size limit: 64 KB.
- Command, notes, filename aur history validate hote hain.
- Control characters reject.
- Filename path traversal reject.
- AI actions strict allowlist: `none` / `download_note`.
- `eval`, `exec`, `shell=True` kahin nahi.
- Simple in-memory rate limit per IP.
- CORS configurable.
- Frontend `textContent` use karta hai, `innerHTML` nahi.
- Notes browser/device par; server par user content store nahi.

---

## 12. Limitations

- Free Render plan kabhi-kabhi sleep mode me jata hai; pehli request slow ho sakti hai.
- Voice browser support par depend karta hai; Chrome/Edge best hain.
- Offline AI kaam nahi karega — OpenRouter ko internet chahiye.
- Notes server database me nahi, device par hote hain.
- Koi login/multi-user system nahi hai.
- Notepad / Windows desktop automation is version me nahi hai.
- Rate limiter in-memory hai; multiple instances me Redis chahiye.

---

## 13. Troubleshooting

| Problem | Solution |
|---|---|
| `/health` 404 ya deploy fail | Start command aur health check path check karo |
| `API key missing` | Render Environment me `OPENROUTER_API_KEY` set karo, service restart karo |
| `401 invalid key` | OpenRouter key sahi/active hai ya nahi check karo |
| `404 model` | `OPENROUTER_MODEL` valid model ID se replace karo |
| `429` | OpenRouter ya app rate limit; thodi der wait karo |
| Mic kaam nahi | HTTPS, Chrome/Edge, site mic permission, internet check karo |
| CORS error | `VAKKIAI_ALLOWED_ORIGINS` me frontend origin daalo |
| Notes restart ke baad gayab | Expected — notes device par hote hain; download kar lo |
| App slow first load | Free plan sleep; 20–60 second wait karo ya Starter plan use karo |

---

## 14. Useful links

- Render Web Services: <https://render.com/docs/web-services>
- Render Flask deploy: <https://render.com/docs/deploy-flask>
- Render Blueprint spec: <https://render.com/docs/blueprint-spec>
- OpenRouter API reference: <https://openrouter.ai/docs/api_reference/overview>
- OpenRouter models: <https://openrouter.ai/models>
- MDN Web Speech API: <https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API>
