const els = {
  worldIdea: document.getElementById("worldIdea"),
  generateBtn: document.getElementById("generateBtn"),
  genStatus: document.getElementById("genStatus"),
  worldName: document.getElementById("worldName"),
  geography: document.getElementById("geography"),
  history: document.getElementById("history"),
  creatures: document.getElementById("creatures"),
  magic: document.getElementById("magic"),
  hooks: document.getElementById("hooks"),
  pill: document.getElementById("pill"),
  chat: document.getElementById("chat"),
  chatBox: document.getElementById("chatBox"),
  sendBtn: document.getElementById("sendBtn"),
  chatStatus: document.getElementById("chatStatus"),
  themeToggle: document.getElementById("themeToggle"),
  saveBtn: document.getElementById("saveBtn"),
  downloadBtn: document.getElementById("downloadBtn"),
  savedWorlds: document.getElementById("savedWorlds"),
  loginBtn: document.getElementById("loginBtn"),
  signupBtn: document.getElementById("signupBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  guestBtn: document.getElementById("guestBtn"),
  loginBtnHero: document.getElementById("loginBtnHero"),
  signupBtnHero: document.getElementById("signupBtnHero"),
  guestBtnHero: document.getElementById("guestBtnHero"),
  toast: document.getElementById("toast"),
  // Add these inside the const els = { ... } object
  flashcardBtn: document.getElementById("flashcardBtn"),
  flashcardModal: document.getElementById("flashcard-modal"),
  flashcardClose: document.getElementById("flashcard-close"),
  flashcardGrid: document.getElementById("flashcard-grid"),
};

let currentWorld = null;
let savedWorldId = null;
let currentUser = null;
let sessionStarted = false;

function toast(msg, kind = "info") {
  els.toast.textContent = msg;
  els.toast.classList.add("show");
  els.toast.style.borderColor =
    kind === "err" ? "rgba(255,92,124,.55)" : "rgba(184,140,255,.35)";
  setTimeout(() => els.toast.classList.remove("show"), 2200);
}

function updateAuthUI() {
  const showSession = sessionStarted;
  els.loginBtn.hidden = showSession;
  els.signupBtn.hidden = showSession;
  els.guestBtn.hidden = showSession;
  els.loginBtnHero.hidden = showSession;
  els.signupBtnHero.hidden = showSession;
  els.guestBtnHero.hidden = showSession;
  els.logoutBtn.hidden = !showSession;

  const pill = document.getElementById("user-pill");
  const nameEl = document.getElementById("user-name");
  const avatar = document.getElementById("user-avatar");

  if (showSession) {
    if (currentUser) {
      nameEl.textContent = currentUser.name || currentUser.email || "User";
      if (currentUser.picture) {
        avatar.src = currentUser.picture;
        avatar.hidden = false;
      } else {
        avatar.hidden = true;
      }
    } else {
      nameEl.textContent = "Guest";
      avatar.hidden = true;
    }
    pill.hidden = false;
  } else {
    pill.hidden = true;
  }
}

function showLanding() {
  document.getElementById("hero-banner").hidden = false;
  document.getElementById("features").hidden = false;
  document.getElementById("app-section").hidden = true;
}

function showApp() {
  document.getElementById("hero-banner").hidden = true;
  document.getElementById("features").hidden = true;
  document.getElementById("app-section").hidden = false;
  const target = document.getElementById("worldIdea");
  if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setStatus(el, msg, isErr = false) {
  el.textContent = msg || "";
  el.classList.toggle("err", Boolean(isErr));
}

function setLoading(el, msg) {
  el.innerHTML = msg ? `<span class="spinner"></span>${msg}` : "";
  el.classList.remove("err");
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function renderList(ul, items) {
  ul.innerHTML = "";
  if (!Array.isArray(items)) return;
  for (const it of items) {
    const li = document.createElement("li");
    li.textContent = String(it);
    ul.appendChild(li);
  }
}

function renderCreatures(container, creatures) {
  container.innerHTML = "";
  if (!Array.isArray(creatures)) return;
  for (const c of creatures) {
    const wrap = document.createElement("div");
    wrap.className = "creature";
    wrap.innerHTML = `
      <div class="n">${escapeHtml(c?.name ?? "")}</div>
      <div class="d">${escapeHtml(c?.description ?? "")}</div>
    `;
    container.appendChild(wrap);
  }
}

function renderWorld(world) {
  currentWorld = world;
  els.worldName.textContent = world?.world_name || "Untitled";
  renderList(els.geography, world?.geography);
  renderList(els.history, world?.history);
  renderCreatures(els.creatures, world?.creatures);
  renderList(els.magic, world?.magic_system);
  renderList(els.hooks, world?.plot_hooks);
  els.pill.textContent = world?.world_name || "World loaded";
  els.flashcardBtn.hidden = false;
}

function appendMessage(role, text) {
  const msg = document.createElement("div");
  msg.className = `msg ${role === "user" ? "user" : "assistant"}`;
  msg.innerHTML = `
    <div class="avatar" aria-hidden="true"></div>
    <div class="bubble">${escapeHtml(text)}</div>
  `;
  els.chat.appendChild(msg);
  els.chat.scrollTop = els.chat.scrollHeight;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.error || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

function continueAsGuest() {
  sessionStarted = true;
  currentUser = null;
  updateAuthUI();
  showApp();
  toast("Continuing as guest.");
}

async function fetchCurrentUser() {
  try {
    const data = await api("/auth/user", { method: "GET" });
    if (data.logged_in && data.user) {
      currentUser = data.user;
      sessionStarted = true;
      updateAuthUI();
      showApp();
    } else {
      sessionStarted = false;
      currentUser = null;
      updateAuthUI();
      showLanding();
    }
  } catch (e) {
    sessionStarted = false;
    currentUser = null;
    updateAuthUI();
    showLanding();
  }
}

// FIX: logout navigates to /auth/logout which clears BOTH session["user"] and
// session["user_id"], then redirects home. This works for OAuth and password users.
function handleLogout() {
  window.location.href = "/auth/logout";
}

async function refreshSavedWorlds() {
  els.savedWorlds.innerHTML = `<div class="muted">Loading…</div>`;
  try {
    const data = await api("/api/worlds", { method: "GET" });
    const worlds = data.worlds || [];
    if (!worlds.length) {
      els.savedWorlds.innerHTML = `<div class="muted">No saved worlds yet.</div>`;
      return;
    }
    els.savedWorlds.innerHTML = "";
    for (const w of worlds) {
      const item = document.createElement("div");
      item.className = "saved-item";
      const dt = new Date(w.updated_at_ms || Date.now());
      item.innerHTML = `
        <div>
          <div class="saved-title">${escapeHtml(w.title || "Untitled")}</div>
          <div class="saved-sub">Updated: ${escapeHtml(dt.toLocaleString())}</div>
        </div>
        <div class="saved-actions">
          <button class="btn ghost" data-act="load" data-id="${escapeHtml(w.id)}" type="button">Load</button>
        </div>
      `;
      els.savedWorlds.appendChild(item);
    }
    els.savedWorlds.querySelectorAll("button[data-act='load']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        await loadWorld(id);
      });
    });
  } catch (e) {
    els.savedWorlds.innerHTML = `<div class="muted">Failed to load saved worlds.</div>`;
  }
}

async function generateWorld() {
  const idea = els.worldIdea.value.trim();
  if (!idea) return toast("Type a world idea first.", "err");

  setLoading(els.genStatus, "Forging your world…");
  els.generateBtn.disabled = true;

  try {
    const data = await api("/api/generate-world", {
      method: "POST",
      body: JSON.stringify({ idea }),
    });
    renderWorld(data.world);
    savedWorldId = null;
    els.chat.innerHTML = "";
    appendMessage("assistant", "World created. Ask me anything about it.");
    setStatus(els.genStatus, "World generated.");
    toast("World generated.");
  } catch (e) {
    setStatus(els.genStatus, e.message, true);
    toast(e.message, "err");
  } finally {
    els.generateBtn.disabled = false;
    await refreshSavedWorlds();
  }
}

async function sendChat() {
  const msg = els.chatBox.value.trim();
  if (!msg) return;
  if (!currentWorld) return toast("Generate or load a world first.", "err");

  appendMessage("user", msg);
  els.chatBox.value = "";
  autosize(els.chatBox);

  setLoading(els.chatStatus, "Summoning lore…");
  els.sendBtn.disabled = true;

  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message: msg }),
    });
    appendMessage("assistant", data.reply || "");
    setStatus(els.chatStatus, "");
  } catch (e) {
    setStatus(els.chatStatus, e.message, true);
    appendMessage("assistant", `Error: ${e.message}`);
  } finally {
    els.sendBtn.disabled = false;
  }
}

async function saveWorld() {
  if (!currentUser) return toast("Please sign in to save your world.", "err");
  if (!currentWorld) return toast("No world to save.", "err");
  const title = prompt("Save as (title):", currentWorld.world_name || "My World");
  if (title === null) return;
  setLoading(els.genStatus, "Saving…");
  try {
    const data = await api("/api/worlds/save", {
      method: "POST",
      body: JSON.stringify({ title, id: savedWorldId }),
    });
    savedWorldId = data?.saved?.id || savedWorldId;
    setStatus(els.genStatus, "Saved.");
    toast("Saved.");
  } catch (e) {
    setStatus(els.genStatus, e.message, true);
    toast(e.message, "err");
  } finally {
    await refreshSavedWorlds();
  }
}

async function loadWorld(id) {
  setLoading(els.genStatus, "Loading saved world…");
  try {
    const data = await api("/api/worlds/load", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    renderWorld(data.world);
    savedWorldId = data?.meta?.id || id;
    els.chat.innerHTML = "";
    appendMessage(
      "assistant",
      `Loaded "${data?.world?.world_name || "world"}". Ask me anything.`
    );
    setStatus(els.genStatus, "Loaded.");
    toast("Loaded.");
  } catch (e) {
    setStatus(els.genStatus, e.message, true);
    toast(e.message, "err");
  }
}

function downloadWorld() {
  if (!savedWorldId) return toast("Save the world first, then download.", "err");
  window.location.href = `/api/worlds/download/${encodeURIComponent(savedWorldId)}.txt`;
}

function autosize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
}

function initTheme() {
  const saved = localStorage.getItem("afwd_theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
}

function toggleTheme() {
  const cur = document.documentElement.getAttribute("data-theme") || "dark";
  const next = cur === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("afwd_theme", next);
  toast(`Theme: ${next}`);
}

function openFlashcards() {
  if (!currentWorld) return toast("No world loaded.", "err");
  
  els.flashcardGrid.innerHTML = ""; // Clear old cards

  // Clean, text-only card generator
  const createCard = (frontText, backText) => {
    if (!backText) return; 
    const card = document.createElement("div");
    card.className = "flashcard";
    card.innerHTML = `
      <div class="flashcard-inner">
        <div class="flashcard-front">${escapeHtml(frontText)}</div>
        <div class="flashcard-back">${escapeHtml(backText)}</div>
      </div>
    `;
    // Flip behavior on click
    card.addEventListener("click", () => card.classList.toggle("flipped"));
    els.flashcardGrid.appendChild(card);
  };

  // Generate the cards from the current world data
  if (Array.isArray(currentWorld.creatures)) {
    currentWorld.creatures.forEach(c => createCard(c.name, c.description));
  }
  if (Array.isArray(currentWorld.geography)) {
    currentWorld.geography.forEach((item, i) => createCard(`Geography #${i+1}`, item));
  }
  if (Array.isArray(currentWorld.history)) {
    currentWorld.history.forEach((item, i) => createCard(`History #${i+1}`, item));
  }
  if (Array.isArray(currentWorld.magic_system)) {
    currentWorld.magic_system.forEach((item, i) => createCard(`Magic #${i+1}`, item));
  }

  // Show the modal
  els.flashcardModal.classList.remove("hidden");
}

function closeFlashcards() {
  els.flashcardModal.classList.add("hidden");
}

// ── Event listeners ──────────────────────────────────────────────────────────

els.generateBtn.addEventListener("click", generateWorld);
els.worldIdea.addEventListener("keydown", (e) => {
  if (e.key === "Enter") generateWorld();
});
els.sendBtn.addEventListener("click", sendChat);
els.chatBox.addEventListener("input", () => autosize(els.chatBox));
els.chatBox.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
});
els.themeToggle.addEventListener("click", toggleTheme);
els.guestBtn.addEventListener("click", continueAsGuest);
els.guestBtnHero.addEventListener("click", continueAsGuest);
els.saveBtn.addEventListener("click", saveWorld);
els.downloadBtn.addEventListener("click", downloadWorld);

els.flashcardBtn.addEventListener("click", openFlashcards);
els.flashcardClose.addEventListener("click", closeFlashcards);

// Close modal if user clicks the dark background outside the modal
els.flashcardModal.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal-backdrop")) {
    closeFlashcards();
  }
});

// FIX: logoutBtn previously had NO click handler — added here
els.logoutBtn.addEventListener("click", handleLogout);

// ── Boot ─────────────────────────────────────────────────────────────────────

initTheme();
autosize(els.chatBox);
fetchCurrentUser();
refreshSavedWorlds();
appendMessage("assistant", "Describe a world idea, then click Generate.");