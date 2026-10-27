# VakkiAI Web — Render Live Deployment Guide (Tablet se)

Ye guide **Xiaomi Pad 8 / Redmi Android tablet** jaise device ke liye hai. Isme Windows PC ki zarurat nahi. Bas Chrome browser, GitHub account, Render account aur OpenRouter API key chahiye.

> **Note:** Is chat environment me Render aur GitHub connectors available nahi hain. Isliye main yahan se direct repo create/deploy nahi kar sakta. Mainne poora deploy-ready code taiyar kar diya hai; neeche ke steps aap tablet par follow karo.

---

## A. Pehle taiyari

1. **OpenRouter API key** lo: <https://openrouter.ai/settings/keys>
2. Key ko kisi safe jagah note karo. **Use chat/WhatsApp me share mat karo.**
3. `VakkiAI-Web-Render-Deploy.zip` download karo aur tablet me extract karo.
   - `Files by Google`, `ZArchiver`, ya koi bhi file manager use kar sakte ho.
4. Extract hone ke baad folder me ye dikhenge:
   ```text
   app.py
   render.yaml
   Procfile
   requirements.txt
   README.md
   DEPLOY-RENDER.md
   backend/
   frontend/
   tests/ (optional)
   ```
   Hidden files jaise `.env.example`, `.gitignore`, `.python-version` optional hain; deployment ke liye zaroori nahi.

---

## B. GitHub repo banao (tablet Chrome se)

1. Chrome me kholo: <https://github.com/new>
2. **Repository name:** `vakkiai-web`
3. **Public** select karo.
4. **Add a README file** optional hai; agar select kiya to baad me overwrite ho jayega.
5. **Create repository** dabao.
6. Repo ke andar **Add file → Upload files** par jao.
7. Extract kiye hue folder ke **saare files aur folders** select karke upload karo.
   - Important: `backend/` aur `frontend/` folders ke andar ka content bhi upload ho.
   - `render.yaml` root par hona chahiye.
8. Neeche **Commit changes** dabao.

Agar mobile browser me folder upload problematic lage, to `frontend/` aur `backend/` ke files ko ek-ek karke upload karo. GitHub web UI hidden files bhi allow karta hai, par deployment ke liye unki zarurat nahi.

---

## C. Render par Blueprint deploy karo

1. Chrome me kholo: <https://dashboard.render.com/>
2. Sign in / sign up karo.
3. **New → Blueprint** select karo.
4. GitHub account connect karo aur `vakkiai-web` repo choose karo.
5. Render `render.yaml` read karega. Service name dikhega: `vakkiai-web`.
6. Prompt aayega:
   ```text
   OPENROUTER_API_KEY
   ```
   Yahan apni real key paste karo. Ye value Git me save nahi hogi.
7. Baaki values default rehne do:
   - `OPENROUTER_MODEL=openai/gpt-4o-mini`
   - `PYTHON_VERSION=3.12`
   - `VAKKIAI_DEFAULT_LANGUAGE=hi-IN`
   - `VAKKIAI_ALLOWED_ORIGINS=*`
8. **Apply / Create Resources** dabao.
9. 3–6 minute wait karo. Logs me `Booting worker` aur health check success dikhega.
10. URL milega, jaise:
    ```text
    https://vakkiai-web.onrender.com
    ```

---

## D. Health check

Browser me kholo:

```text
https://vakkiai-web.onrender.com/health
```

Expected response:

```json
{
  "status": "ok",
  "live_mode": true,
  "api_key_configured": true,
  "model": "openai/gpt-4o-mini"
}
```

Agar `api_key_configured: false` hai, to Render → Service → Environment me `OPENROUTER_API_KEY` set karo aur **Manual Deploy → Clear build cache & deploy** karo.

---

## E. Tablet par app use karo

1. Chrome me service URL kholo.
2. Pehli baar free plan slow ho sakta hai; 30–60 second wait karo.
3. Text command likho ya **Start voice** dabao.
4. Mic permission aaye to **Allow** karo.
5. Response ke saath notes aaye to:
   - **Save on tablet** → device storage
   - **Download .md** → Downloads folder
6. Chrome menu ⋮ → **Add to Home screen** se PWA install kar sakte ho.

---

## F. Frontend aur backend alag platform par

Agar aap frontend ko alag platform par post karna chahte ho (Netlify, GitHub Pages, Cloudflare Pages, etc.) aur backend Render par rakhna chahte ho:

1. Backend pehle Render par deploy karo.
2. Backend URL copy karo, jaise `https://vakkiai-api.onrender.com`.
3. `frontend/config.js` me likho:
   ```js
   window.VAKKIAI_API_BASE = "https://vakkiai-api.onrender.com";
   ```
   Ya deployed app ke **Backend settings** card me URL daal kar **Save URL** karo.
4. Render backend environment me set karo:
   ```dotenv
   VAKKIAI_ALLOWED_ORIGINS=https://your-frontend-domain.com
   ```
5. Frontend static host par `frontend/` folder upload karo.

> Kabhi bhi API key frontend config me mat daalo.

---

## G. Manual Web Service (Blueprint ke bina)

Agar Blueprint use nahi karna:

| Field | Value |
|---|---|
| New | Web Service |
| Language | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120` |
| Health Check Path | `/health` |
| Plan | Free / Starter |

Environment variables same as section C.

---

## H. Common errors

| Error | Fix |
|---|---|
| `No open ports detected` | Start command me `--bind 0.0.0.0:$PORT` hona chahiye |
| `Application Error` | Render logs dekho; zyada tar API key ya dependency issue |
| `503 AI configure nahi hai` | `OPENROUTER_API_KEY` set karo |
| `502 OpenRouter HTTP 401` | Key invalid/expired |
| `502 OpenRouter HTTP 404` | Model ID galat |
| Mic `not-allowed` | Chrome lock icon → Permissions → Microphone → Allow |
| Voice `network` | Internet check karo; Web Speech API online hai |
| CORS error | `VAKKIAI_ALLOWED_ORIGINS` me frontend domain daalo |
| Notes missing after redeploy | Expected; notes device par hote hain, server par nahi |

---

## I. Security checklist

- [ ] `.env` Git me upload nahi kiya.
- [ ] `render.yaml` me `OPENROUTER_API_KEY` ka value nahi likha, sirf `sync: false`.
- [ ] API key sirf Render Dashboard me.
- [ ] `VAKKIAI_ALLOWED_ORIGINS` production me `*` se specific domain kiya.
- [ ] `/health` par `api_key_configured: true`.
- [ ] HTTPS URL use ho raha hai.
- [ ] Mic permission sirf trusted site ko diya.

---

## J. Next step

Deploy hone ke baad mujhe **sirf service ka public URL** bhejo — API key mat bhejna. Main uske endpoints, frontend config aur next features ka plan verify kar dunga.
