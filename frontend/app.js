/* VakkiAI Web frontend — vanilla JS, no CDN, no build step.
   API key kabhi browser me nahi aati; sirf backend se /api/chat call hota hai. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    statusDot: $("statusDot"),
    statusText: $("statusText"),
    chat: $("chat"),
    command: $("command"),
    charCount: $("charCount"),
    sendBtn: $("sendBtn"),
    voiceStartBtn: $("voiceStartBtn"),
    voiceStopBtn: $("voiceStopBtn"),
    cancelBtn: $("cancelBtn"),
    clearBtn: $("clearBtn"),
    language: $("language"),
    voiceSupport: $("voiceSupport"),
    notesPanel: $("notesPanel"),
    notesText: $("notesText"),
    noteFilename: $("noteFilename"),
    saveNoteBtn: $("saveNoteBtn"),
    downloadNoteBtn: $("downloadNoteBtn"),
    savedNotes: $("savedNotes"),
    apiBaseInput: $("apiBaseInput"),
    saveApiBtn: $("saveApiBtn"),
    resetApiBtn: $("resetApiBtn"),
    apiStatus: $("apiStatus"),
    configWarning: $("configWarning"),
    offlineBadge: $("offlineBadge"),
    footerMode: $("footerMode"),
  };

  const KEYS = {
    history: "vakkiai.history.v1",
    apiBase: "vakkiai.apiBase.v1",
    notePrefix: "vakkiai.note.v1.",
  };
  const DEFAULT_FILENAME = "vakkiai-note.md";
  const params = new URLSearchParams(window.location.search);

  let apiBase = "";
  let maxCommandChars = 4000;
  let history = [];
  let abortController = null;
  let recognition = null;
  let currentNotes = "";

  function storageGet(key) {
    try { return window.localStorage.getItem(key); } catch (_error) { return null; }
  }
  function storageSet(key, value) {
    try { window.localStorage.setItem(key, value); return true; } catch (_error) { return false; }
  }
  function storageRemove(key) {
    try { window.localStorage.removeItem(key); } catch (_error) { /* ignore */ }
  }
  function storageKeys() {
    try { return Object.keys(window.localStorage); } catch (_error) { return []; }
  }

  function normalizeBase(value) {
    const raw = (value || "").trim();
    if (!raw) return "";
    let candidate = raw;
    if (!/^https?:\/\//i.test(candidate)) candidate = "https://" + candidate;
    try {
      const url = new URL(candidate);
      if (url.protocol !== "http:" && url.protocol !== "https:") return "";
      return url.origin;
    } catch (_error) {
      return "";
    }
  }

  function apiUrl(path) {
    return apiBase ? apiBase + path : path;
  }

  function setStatus(message, kind = "ok") {
    els.statusText.textContent = message;
    els.statusDot.className = "status-dot " + (kind || "ok");
  }

  function setBusy(isBusy) {
    els.sendBtn.disabled = isBusy;
    els.cancelBtn.disabled = !isBusy;
    els.voiceStartBtn.disabled = isBusy || !speechSupported();
    els.clearBtn.disabled = isBusy;
  }

  function updateCharCount() {
    const length = els.command.value.length;
    els.charCount.textContent = length + " / " + maxCommandChars;
    els.charCount.style.color = length > maxCommandChars ? "var(--error)" : "";
  }

  function renderMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;
    const label = document.createElement("span");
    label.className = "role";
    label.textContent = role === "user" ? "You" : role === "assistant" ? "VakkiAI" : role === "error" ? "Error" : "System";
    const body = document.createElement("span");
    body.textContent = String(text || "");
    wrap.appendChild(label);
    wrap.appendChild(body);
    els.chat.appendChild(wrap);
    els.chat.scrollTop = els.chat.scrollHeight;
  }

  function saveHistory() {
    history = history.slice(-8);
    storageSet(KEYS.history, JSON.stringify(history));
  }

  function appendChat(role, text, persist = false) {
    renderMessage(role, text);
    if (persist && (role === "user" || role === "assistant")) {
      history.push({ role, content: String(text || "") });
      saveHistory();
    }
  }

  function loadHistory() {
    try {
      const parsed = JSON.parse(storageGet(KEYS.history) || "[]");
      if (!Array.isArray(parsed)) return;
      history = parsed
        .filter((item) => item && (item.role === "user" || item.role === "assistant") && typeof item.content === "string")
        .slice(-8)
        .map((item) => ({ role: item.role, content: item.content.slice(0, 4000) }));
      history.forEach((item) => renderMessage(item.role, item.content));
    } catch (_error) {
      history = [];
    }
  }

  function safeFilename(value) {
    if (typeof value !== "string") return DEFAULT_FILENAME;
    const name = value.trim();
    if (
      name.length > 0 &&
      name.length <= 100 &&
      /^[A-Za-z0-9._-]+$/.test(name) &&
      /\.(md|txt)$/i.test(name) &&
      !name.startsWith(".") &&
      !name.includes("..") &&
      !name.endsWith(".")
    ) {
      return name;
    }
    return DEFAULT_FILENAME;
  }

  function readableFetchError(error) {
    if (error && error.name === "AbortError") return "Request cancel kar di gayi.";
    if (error instanceof TypeError) {
      return "Backend se connect nahi ho paya. Internet ya Backend URL setting check karo.";
    }
    return (error && error.message) ? error.message : "Unknown network error.";
  }

  async function loadConfig() {
    setStatus("Connecting…", "working");
    try {
      const response = await fetch(apiUrl("/api/config"), { cache: "no-store" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));
      maxCommandChars = Number(data.max_command_chars) || 4000;
      els.command.maxLength = maxCommandChars;
      updateCharCount();
      if (data.default_language) els.language.value = data.default_language;
      els.configWarning.hidden = Boolean(data.has_api_key);
      els.footerMode.textContent = apiBase ? "Split mode" : "Live mode";
      if (!data.has_api_key) {
        setStatus("API key missing", "error");
      } else {
        setStatus("Ready • live", "ok");
      }
    } catch (error) {
      els.configWarning.hidden = true;
      els.footerMode.textContent = apiBase ? "Split mode" : "Live mode";
      setStatus("Backend unreachable", "error");
      appendChat("error", readableFetchError(error));
    }
  }

  async function sendCommand() {
    if (abortController) return;
    const command = els.command.value.trim();
    if (!command) {
      setStatus("Pehle command likho", "error");
      els.command.focus();
      return;
    }
    if (command.length > maxCommandChars) {
      setStatus("Command bahut lambi hai", "error");
      return;
    }

    appendChat("user", command, true);
    els.command.value = "";
    updateCharCount();
    setBusy(true);
    setStatus("AI soch raha hai…", "working");
    abortController = new AbortController();

    try {
      const response = await fetch(apiUrl("/api/chat"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command,
          history: history.slice(-8),
          language: els.language.value,
        }),
        signal: abortController.signal,
        cache: "no-store",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || ("HTTP " + response.status));

      const message = typeof data.message === "string" && data.message.trim()
        ? data.message
        : "AI response empty tha.";
      appendChat("assistant", message, true);

      if (typeof data.notes === "string" && data.notes.trim()) {
        currentNotes = data.notes;
        const filename = safeFilename(data.suggested_filename);
        els.notesText.textContent = currentNotes;
        els.noteFilename.value = filename;
        els.notesPanel.hidden = false;
        if (data.action === "download_note") {
          setStatus("Note ready • Save/Download", "ok");
        } else {
          setStatus("Response + notes ready", "ok");
        }
      } else {
        currentNotes = "";
        els.notesPanel.hidden = true;
        setStatus("Response ready", "ok");
      }
    } catch (error) {
      if (error && error.name === "AbortError") {
        appendChat("system", "Request cancel kar di gayi.");
        setStatus("Cancelled", "ok");
      } else {
        const message = readableFetchError(error);
        appendChat("error", message);
        setStatus("AI request failed", "error");
      }
    } finally {
      abortController = null;
      setBusy(false);
    }
  }

  function cancelRequest() {
    if (abortController) abortController.abort();
  }

  function clearConversation() {
    if (!window.confirm("Conversation clear karein? Saved notes delete nahi hongi.")) return;
    els.chat.replaceChildren();
    history = [];
    storageRemove(KEYS.history);
    currentNotes = "";
    els.notesPanel.hidden = true;
    els.command.value = "";
    updateCharCount();
    appendChat("system", "Conversation clear kar di gayi. Naya command likho.");
    setStatus("Ready", "ok");
  }

  const SpeechRecognitionClass = window.SpeechRecognition || window.webkitSpeechRecognition;
  function speechSupported() {
    return Boolean(SpeechRecognitionClass);
  }

  function updateVoiceSupport() {
    if (!speechSupported()) {
      els.voiceSupport.textContent = "Voice unsupported • text use karo";
      els.voiceStartBtn.disabled = true;
      return;
    }
    if (!window.isSecureContext) {
      els.voiceSupport.textContent = "Voice needs HTTPS • text use karo";
      return;
    }
    els.voiceSupport.textContent = "Voice ready • Chrome/Edge recommended";
  }

  function voiceErrorMessage(code) {
    const messages = {
      "not-allowed": "Microphone permission nahi mili. Chrome address bar ke lock icon se Mic Allow karo.",
      "service-not-allowed": "Speech service allowed nahi hai. HTTPS aur browser settings check karo.",
      "network": "Speech recognition ke liye internet chahiye; connection check karo.",
      "no-speech": "Awaaz samajh nahi aayi; thodi der baad dobara bolo.",
      "audio-capture": "Microphone available nahi hai; tablet mic check karo.",
      "aborted": "Voice input band kar diya gaya.",
    };
    return messages[code] || ("Voice error: " + (code || "unknown"));
  }

  function appendToCommand(text) {
    const existing = els.command.value.trim();
    const combined = existing ? existing + "\n" + text : text;
    els.command.value = combined.slice(0, maxCommandChars);
    updateCharCount();
    els.command.focus();
  }

  function startVoice() {
    if (!speechSupported() || recognition || abortController) return;
    recognition = new SpeechRecognitionClass();
    recognition.lang = els.language.value || "hi-IN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      els.voiceStartBtn.disabled = true;
      els.voiceStopBtn.disabled = false;
      setStatus("Mic chal raha hai… bolo", "working");
    };
    recognition.onresult = (event) => {
      let text = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        if (event.results[i].isFinal) text += event.results[i][0].transcript;
      }
      if (text.trim()) appendToCommand(text.trim());
    };
    recognition.onerror = (event) => {
      const message = voiceErrorMessage(event.error);
      appendChat("error", message);
      setStatus("Voice failed", "error");
    };
    recognition.onend = () => {
      recognition = null;
      els.voiceStartBtn.disabled = Boolean(abortController);
      els.voiceStopBtn.disabled = true;
      if (els.statusText.textContent.indexOf("Mic chal") === 0) setStatus("Voice band", "ok");
    };

    try {
      recognition.start();
    } catch (error) {
      recognition = null;
      appendChat("error", "Voice start nahi ho paya: " + (error.message || "unknown"));
      setStatus("Voice failed", "error");
    }
  }

  function stopVoice() {
    if (recognition) {
      try { recognition.stop(); } catch (_error) { /* ignore */ }
    }
  }

  function saveCurrentNote() {
    if (!currentNotes.trim()) {
      setStatus("Save karne ke liye notes nahi hain", "error");
      return;
    }
    const filename = safeFilename(els.noteFilename.value);
    els.noteFilename.value = filename;
    const item = {
      filename,
      text: currentNotes,
      updatedAt: new Date().toISOString(),
    };
    if (!storageSet(KEYS.notePrefix + filename, JSON.stringify(item))) {
      appendChat("error", "Tablet storage available nahi hai; Download use karo.");
      return;
    }
    renderSavedNotes();
    appendChat("system", "Note tablet me save ho gayi: " + filename);
    setStatus("Note saved locally", "ok");
  }

  function downloadText(filename, text) {
    const safe = safeFilename(filename);
    const blob = new Blob([text.trim() + "\n"], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = safe;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadCurrentNote() {
    if (!currentNotes.trim()) {
      setStatus("Download karne ke liye notes nahi hain", "error");
      return;
    }
    downloadText(els.noteFilename.value, currentNotes);
    setStatus("Note download shuru", "ok");
  }

  function renderSavedNotes() {
    els.savedNotes.replaceChildren();
    const items = [];
    for (const key of storageKeys()) {
      if (!key.startsWith(KEYS.notePrefix)) continue;
      try {
        const item = JSON.parse(storageGet(key) || "null");
        if (item && typeof item.filename === "string" && typeof item.text === "string") {
          items.push({ key, ...item });
        }
      } catch (_error) { /* ignore corrupt entry */ }
    }
    items.sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
    if (items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "Abhi koi saved note nahi hai.";
      els.savedNotes.appendChild(empty);
      return;
    }
    for (const item of items.slice(0, 20)) {
      const row = document.createElement("div");
      row.className = "saved-note";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = item.filename;
      const actions = document.createElement("span");
      actions.className = "actions";
      const download = document.createElement("button");
      download.type = "button";
      download.textContent = "Download";
      download.addEventListener("click", () => downloadText(item.filename, item.text));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "danger";
      remove.textContent = "Delete";
      remove.addEventListener("click", () => {
        if (!window.confirm("Ye note tablet se delete karein?")) return;
        storageRemove(item.key);
        renderSavedNotes();
      });
      actions.appendChild(download);
      actions.appendChild(remove);
      row.appendChild(name);
      row.appendChild(actions);
      els.savedNotes.appendChild(row);
    }
  }

  function updateApiUi() {
    els.apiBaseInput.value = apiBase;
    els.apiStatus.textContent = apiBase
      ? "Using backend: " + apiBase
      : "Using same domain (recommended for one Render service).";
  }

  function saveApiBase() {
    const normalized = normalizeBase(els.apiBaseInput.value);
    if (!normalized && els.apiBaseInput.value.trim()) {
      els.apiStatus.textContent = "URL valid nahi hai. Example: https://your-service.onrender.com";
      setStatus("Backend URL invalid", "error");
      return;
    }
    apiBase = normalized;
    if (apiBase) storageSet(KEYS.apiBase, apiBase);
    else storageRemove(KEYS.apiBase);
    updateApiUi();
    loadConfig();
  }

  function resetApiBase() {
    apiBase = normalizeBase(window.VAKKIAI_API_BASE || "");
    if (apiBase) storageSet(KEYS.apiBase, apiBase);
    else storageRemove(KEYS.apiBase);
    updateApiUi();
    loadConfig();
  }

  function updateOnlineStatus() {
    els.offlineBadge.hidden = navigator.onLine;
    if (!navigator.onLine) setStatus("Offline", "error");
  }

  function registerServiceWorker() {
    if ("serviceWorker" in navigator && window.location.protocol === "https:") {
      window.addEventListener("load", () => {
        navigator.serviceWorker.register("./sw.js").catch(() => { /* optional */ });
      });
    }
  }

  function init() {
    apiBase = normalizeBase(
      params.get("api") || storageGet(KEYS.apiBase) || window.VAKKIAI_API_BASE || ""
    );
    const configuredLanguage = window.VAKKIAI_DEFAULT_LANGUAGE;
    if (configuredLanguage) els.language.value = configuredLanguage;
    updateApiUi();
    loadHistory();
    if (els.chat.children.length === 0) {
      appendChat("system", "VakkiAI Web live mode me ready. Command likho ya Start voice dabao.");
    }
    renderSavedNotes();
    updateVoiceSupport();
    updateOnlineStatus();
    updateCharCount();
    registerServiceWorker();

    els.command.addEventListener("input", updateCharCount);
    els.sendBtn.addEventListener("click", sendCommand);
    els.cancelBtn.addEventListener("click", cancelRequest);
    els.clearBtn.addEventListener("click", clearConversation);
    els.voiceStartBtn.addEventListener("click", startVoice);
    els.voiceStopBtn.addEventListener("click", stopVoice);
    els.saveNoteBtn.addEventListener("click", saveCurrentNote);
    els.downloadNoteBtn.addEventListener("click", downloadCurrentNote);
    els.saveApiBtn.addEventListener("click", saveApiBase);
    els.resetApiBtn.addEventListener("click", resetApiBase);
    window.addEventListener("online", updateOnlineStatus);
    window.addEventListener("offline", updateOnlineStatus);
    els.command.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        sendCommand();
      }
    });

    loadConfig();
  }

  init();
})();
