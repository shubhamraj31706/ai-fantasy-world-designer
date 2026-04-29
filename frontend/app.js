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
      <div class="creature-header">
        <div class="n">${escapeHtml(c?.name ?? "")}</div>
        <button class="btn ghost btn-sm visualize-btn" data-name="${escapeHtml(c?.name ?? "")}" data-desc="${escapeHtml(c?.description ?? "")}" type="button">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
          Visualize
        </button>
      </div>
      <div class="d">${escapeHtml(c?.description ?? "")}</div>
      <div class="creature-img-wrapper" hidden>
        <img class="creature-img" src="" alt="AI generated creature" hidden />
        <div class="img-status muted">Conjuring image...</div>
      </div>
    `;
    container.appendChild(wrap);
  }

  // Wire up the new Visualize buttons
  container.querySelectorAll(".visualize-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.getAttribute("data-name");
      const desc = btn.getAttribute("data-desc");
      const wrapper = btn.parentElement.parentElement.querySelector(".creature-img-wrapper");
      const img = wrapper.querySelector(".creature-img");
      const status = wrapper.querySelector(".img-status");

      // Set UI to loading state
      btn.disabled = true;
      wrapper.hidden = false;
      img.hidden = true;
      status.hidden = false;
      status.textContent = "Conjuring high-fantasy image...";
      status.classList.remove("err");

      try {
        const data = await api("/api/generate-image", {
          method: "POST",
          body: JSON.stringify({ name, description: desc }),
        });

        if (data.image_url) {
          // 1. ALWAYS attach listeners first!
          img.onload = () => {
            img.hidden = false;
            status.hidden = true;
            btn.disabled = false;
          };
          
          img.onerror = () => {
            status.textContent = "Image magic fizzled. Try again.";
            status.classList.add("err");
            img.hidden = true;
            btn.disabled = false;
          };

          // 2. THEN set the source to trigger the download
          img.src = data.image_url;

        } else {
          throw new Error("No image returned by the oracle.");
        }
      } catch (e) {
        status.textContent = "Failed to conjure image.";
        status.classList.add("err");
        btn.disabled = false;
      }
    });
  });
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
          <button class="btn ghost icon-btn delete-btn" data-act="delete" data-id="${escapeHtml(w.id)}" type="button" title="Delete World">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </button>
          <button class="btn ghost" data-act="load" data-id="${escapeHtml(w.id)}" type="button">Load</button>
        </div>
      `;
      els.savedWorlds.appendChild(item);
    }
    
    // Listen for Load clicks
    els.savedWorlds.querySelectorAll("button[data-act='load']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        await loadWorld(id);
      });
    });

    // Listen for Delete clicks
    els.savedWorlds.querySelectorAll("button[data-act='delete']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        if (confirm("Are you sure you want to destroy this world? This magic cannot be undone.")) {
          try {
            await api("/api/worlds/delete", {
              method: "POST",
              body: JSON.stringify({ id }),
            });
            toast("World destroyed.");
            // If they delete the world they are currently looking at, wipe the screen
            if (savedWorldId === id) {
              savedWorldId = null;
              currentWorld = null;
              els.worldName.textContent = "No world forged yet.";
              els.geography.innerHTML = "";
              els.history.innerHTML = "";
              els.creatures.innerHTML = "";
              els.magic.innerHTML = "";
              els.hooks.innerHTML = "";
              els.chat.innerHTML = "";
              els.pill.textContent = "No world";
              els.flashcardBtn.hidden = true;
            }
            await refreshSavedWorlds(); // Refresh the list immediately
          } catch (e) {
            toast(e.message, "err");
          }
        }
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

async function downloadWorld() {
  if (!savedWorldId) return toast("Save the world first, then download.", "err");

  try {
    // 1. Fetch the text file from your Flask backend
    const response = await fetch(`/api/worlds/download/${encodeURIComponent(savedWorldId)}.txt`);
    
    if (!response.ok) {
      throw new Error("Failed to fetch the file from the server.");
    }

    // 2. Convert the response to a Blob (a raw file object)
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    
    // 3. Create a hidden link to trigger the download
    const a = document.createElement("a");
    a.style.display = "none";
    a.href = url;
    
    // Clean up the filename so it is safe for all operating systems
    const safeName = (currentWorld?.world_name || "fantasy_world")
      .replace(/[^a-z0-9]/gi, '_')
      .toLowerCase();
    a.download = `${safeName}_lore.txt`;
    
    // 4. Click it and clean up the DOM
    document.body.appendChild(a);
    a.click();
    
    window.URL.revokeObjectURL(url);
    a.remove();
    
    toast("Download complete!");
  } catch (e) {
    toast(e.message, "err");
  }
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
// Make the prompt box auto-resize when typing
els.worldIdea.addEventListener("input", () => autosize(els.worldIdea));

// Handle Enter key for the prompt box
els.worldIdea.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault(); // Prevents adding a blank new line
    generateWorld();
  }
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
autosize(els.worldIdea);
fetchCurrentUser();
refreshSavedWorlds();
appendMessage("assistant", "Describe a world idea, then click Generate.");