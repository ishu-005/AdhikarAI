const sendBtn = document.getElementById("sendBtn");
const composerInput = document.getElementById("composerInput");
const messagesEl = document.getElementById("messages");
const threadListEl = document.getElementById("threadList");
const newChatBtn = document.getElementById("newChatBtn");
const themeToggleBtn = document.getElementById("themeToggleBtn");
const insightsToggleBtn = document.getElementById("insightsToggleBtn");
const insightsHeadToggleBtn = document.getElementById("insightsHeadToggleBtn");
const insightsPanelEl = document.getElementById("insightsPanel");
const chatTitleEl = document.getElementById("chatTitle");
const healthBadgeEl = document.getElementById("healthBadge");
const citationsEl = document.getElementById("citations");
const liveSourcesEl = document.getElementById("liveSources");
const sourcesEl = document.getElementById("sources");
const citationCountEl = document.getElementById("citationCount");
const liveCountEl = document.getElementById("liveCount");
const sourceCountEl = document.getElementById("sourceCount");
const domainBadge = document.getElementById("domainBadge");
const languageBadge = document.getElementById("languageBadge");
const contextNoticeEl = document.getElementById("contextNotice");
const messageTpl = document.getElementById("messageTpl");
const uploadBtn = document.getElementById("uploadBtn");
const uploadDomainEl = document.getElementById("uploadDomain");
const uploadFileEl = document.getElementById("uploadFile");
const uploadStatusEl = document.getElementById("uploadStatus");
const composerMetaEl = document.getElementById("composerMeta");

const THREAD_STORAGE_KEY = "adhikarai_threads_v1";
const THEME_STORAGE_KEY = "adhikarai_theme_v1";
const state = {
  conversationId: "",
  messages: [],
  threads: [],
  theme: "dark",
  isSending: false,
  insightsOpen: false,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function languageLabel(language) {
  if (language === "hi") {
    return "Hindi";
  }
  if (language === "en") {
    return "English";
  }
  return "-";
}

function detectInputLanguage(question) {
  if (/\p{Script=Devanagari}/u.test(question)) {
    return "hi";
  }
  return "en";
}

function summarizeTitle(input) {
  const clean = (input || "").trim().replace(/\s+/g, " ");
  if (!clean) {
    return "New legal chat";
  }
  return clean.length > 48 ? `${clean.slice(0, 48)}...` : clean;
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function loadThreads() {
  try {
    const parsed = JSON.parse(localStorage.getItem(THREAD_STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item) => item && typeof item.id === "string");
  } catch {
    return [];
  }
}

function saveThreads() {
  localStorage.setItem(THREAD_STORAGE_KEY, JSON.stringify(state.threads));
}

function saveTheme() {
  localStorage.setItem(THEME_STORAGE_KEY, state.theme);
}

function applyTheme(theme) {
  state.theme = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", state.theme);
  const nextLabel = state.theme === "dark" ? "Light" : "Dark";
  themeToggleBtn.textContent = nextLabel;
  themeToggleBtn.setAttribute("title", `Switch to ${nextLabel.toLowerCase()} theme`);
  themeToggleBtn.setAttribute("aria-label", `Switch to ${nextLabel.toLowerCase()} theme`);
  saveTheme();
}

function toggleTheme() {
  applyTheme(state.theme === "dark" ? "light" : "dark");
}

function loadTheme() {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  applyTheme(saved === "light" ? "light" : "dark");
}

function setInsightsOpen(isOpen) {
  state.insightsOpen = !!isOpen;
  insightsPanelEl.classList.toggle("open", state.insightsOpen);
  insightsPanelEl.setAttribute("aria-hidden", state.insightsOpen ? "false" : "true");
  insightsToggleBtn.setAttribute("aria-expanded", state.insightsOpen ? "true" : "false");
  insightsToggleBtn.classList.toggle("active", state.insightsOpen);
}

function toggleInsights() {
  setInsightsOpen(!state.insightsOpen);
}

function bindCollapsibles() {
  document.querySelectorAll("[data-collapsible]").forEach((section) => {
    const toggle = section.querySelector(".collapse-toggle");
    if (!toggle) {
      return;
    }

    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", expanded ? "false" : "true");
      section.classList.toggle("collapsed", expanded);
    });
  });
}

function updateComposerMeta() {
  const length = composerInput.value.trim().length;
  composerMetaEl.textContent = `${length} chars`;
}

function autoResizeComposer() {
  composerInput.style.height = "auto";
  composerInput.style.height = `${Math.min(composerInput.scrollHeight, 240)}px`;
}

function updateSendState() {
  const hasText = composerInput.value.trim().length > 0;
  sendBtn.disabled = state.isSending || !hasText;
}

function setHealthStatus(kind, label) {
  healthBadgeEl.textContent = `status: ${label}`;
  healthBadgeEl.className = `status-badge status-${kind}`;
}

async function fetchHealth() {
  setHealthStatus("idle", "checking");
  try {
    const resp = await fetch("/api/health");
    const data = await resp.json();
    if (!resp.ok || data.status !== "ok") {
      throw new Error("unhealthy");
    }
    setHealthStatus("ok", "ready");
  } catch {
    setHealthStatus("error", "degraded");
  }
}

function upsertThread(patch) {
  const idx = state.threads.findIndex((item) => item.id === patch.id);
  if (idx === -1) {
    state.threads.unshift(patch);
  } else {
    state.threads[idx] = { ...state.threads[idx], ...patch };
    const [current] = state.threads.splice(idx, 1);
    state.threads.unshift(current);
  }
  saveThreads();
  renderThreadList();
}

function renderThreadList() {
  if (!state.threads.length) {
    threadListEl.innerHTML = '<li class="thread-empty muted">No chats yet.</li>';
    return;
  }

  threadListEl.innerHTML = state.threads
    .map((thread) => {
      const activeClass = thread.id === state.conversationId ? "thread-item active" : "thread-item";
      return `
        <li class="thread-row">
          <button class="${activeClass}" type="button" data-thread-id="${escapeHtml(thread.id)}">
            <p class="thread-title">${escapeHtml(thread.title || "New legal chat")}</p>
            <p class="thread-preview">${escapeHtml(thread.preview || "No messages yet")}</p>
            <p class="thread-meta">${escapeHtml(formatTime(thread.updatedAt || ""))}</p>
          </button>
          <button class="thread-delete" type="button" data-delete-thread-id="${escapeHtml(thread.id)}" aria-label="Delete chat">Delete</button>
        </li>
      `;
    })
    .join("");
}

async function deleteThread(threadId) {
  const target = state.threads.find((item) => item.id === threadId);
  if (!target) {
    return;
  }

  const ok = window.confirm("Delete this chat from the sidebar? This action cannot be undone.");
  if (!ok) {
    return;
  }

  state.threads = state.threads.filter((item) => item.id !== threadId);
  saveThreads();

  if (state.conversationId === threadId) {
    if (state.threads.length) {
      await loadConversation(state.threads[0].id);
    } else {
      await createNewChat();
    }
  } else {
    renderThreadList();
  }
}

function renderConfiguredSources(items) {
  sourceCountEl.textContent = String(items.length || 0);
  if (!items.length) {
    sourcesEl.innerHTML = '<li class="source-card"><p>No dynamic sources configured.</p></li>';
    return;
  }

  sourcesEl.innerHTML = items
    .map(
      (item) => `
      <li class="source-card">
        <h3>${escapeHtml(item.label || "Source")}</h3>
        <p>Domain: ${escapeHtml(item.domain || "-")}</p>
        <p><a href="${escapeHtml(item.url || "")}" target="_blank" rel="noreferrer">${escapeHtml(item.url || "")}</a></p>
      </li>
    `
    )
    .join("");
}

function renderCitations(citations) {
  citationCountEl.textContent = String((citations || []).length);
  if (!citations || citations.length === 0) {
    citationsEl.innerHTML = '<li class="citation-item"><p>No citations for this response.</p></li>';
    return;
  }

  citationsEl.innerHTML = citations
    .map(
      (item) => `
      <li class="citation-item">
        <p class="citation-title">#${escapeHtml(item.id ?? "-")} ${escapeHtml(item.section || "Reference")}</p>
        <p class="citation-meta">${escapeHtml(item.domain || "-")} | ${escapeHtml(item.source || "-")} | score: ${escapeHtml(item.score ?? "n/a")}</p>
      </li>
    `
    )
    .join("");
}

function renderLiveSources(items) {
  liveCountEl.textContent = String((items || []).length);
  if (!items || items.length === 0) {
    liveSourcesEl.innerHTML = '<article class="live-card"><p>No live source fetch for this query.</p></article>';
    return;
  }

  liveSourcesEl.innerHTML = items
    .map(
      (item) => `
      <article class="live-card">
        <h3>${escapeHtml(item.label || "Source")}</h3>
        <p><a href="${escapeHtml(item.url || "")}" target="_blank" rel="noreferrer">Open source</a></p>
        <p>${escapeHtml((item.snippet || "").slice(0, 260))}...</p>
      </article>
    `
    )
    .join("");
}

function renderMessages() {
  if (!state.messages.length) {
    messagesEl.innerHTML = '<p class="msg-empty muted">Start typing to begin this legal chat.</p>';
    return;
  }

  messagesEl.innerHTML = "";
  state.messages.forEach((message) => {
    const node = messageTpl.content.cloneNode(true);
    const article = node.querySelector(".msg");
    const roleEl = node.querySelector(".msg-role");
    const bodyEl = node.querySelector(".msg-body");

    article.classList.add(`msg-${message.role}`);
    if (message.isTyping) {
      article.classList.add("msg-typing");
    }
    roleEl.textContent = message.role === "assistant" ? "Assistant" : "You";
    if (message.isTyping) {
      bodyEl.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
    } else {
      bodyEl.textContent = message.content;
    }
    messagesEl.appendChild(node);
  });

  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setHeaderFromThread() {
  const thread = state.threads.find((item) => item.id === state.conversationId);
  chatTitleEl.textContent = thread?.title || "New legal chat";
}

function resetInsights() {
  domainBadge.textContent = "domain: -";
  domainBadge.classList.add("muted");
  languageBadge.textContent = "language: -";
  languageBadge.classList.add("muted");
  contextNoticeEl.textContent = "Source: -";
  renderCitations([]);
  renderLiveSources([]);
}

function appendMessage(role, content, options = {}) {
  state.messages.push({ role, content, ...options });
  renderMessages();
}

function removeTypingMessage() {
  const idx = state.messages.findIndex((message) => message.isTyping);
  if (idx !== -1) {
    state.messages.splice(idx, 1);
    renderMessages();
  }
}

async function fetchSources() {
  try {
    const resp = await fetch("/api/sources");
    const data = await resp.json();
    renderConfiguredSources(data.dynamic_sources || []);
  } catch (err) {
    sourcesEl.innerHTML = `<li class="source-card"><p>Could not load sources: ${escapeHtml(err.message)}</p></li>`;
  }
}

async function fetchDomains() {
  try {
    const resp = await fetch("/api/domains");
    const data = await resp.json();
    const domains = data.domains || [];
    if (!domains.length) {
      return;
    }
    const selected = uploadDomainEl.value;
    uploadDomainEl.innerHTML = domains
      .map((domain) => `<option value="${escapeHtml(domain)}">${escapeHtml(domain)}</option>`)
      .join("");
    if (domains.includes(selected)) {
      uploadDomainEl.value = selected;
    }
  } catch (err) {
    console.warn("Could not load domains", err);
  }
}

async function uploadPdf() {
  const domain = uploadDomainEl.value;
  const file = uploadFileEl.files?.[0];

  if (!file) {
    uploadStatusEl.textContent = "Please choose a PDF file first.";
    return;
  }

  const formData = new FormData();
  formData.append("domain", domain);
  formData.append("pdf", file);

  uploadBtn.disabled = true;
  uploadBtn.textContent = "Uploading...";

  try {
    const resp = await fetch("/api/upload-pdf", {
      method: "POST",
      body: formData,
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || data.error || "Upload failed");
    }

    uploadStatusEl.textContent = `Uploaded ${data.filename} to ${data.saved_to}`;
    uploadFileEl.value = "";
  } catch (err) {
    uploadStatusEl.textContent = `Upload error: ${err.message}`;
  } finally {
    uploadBtn.disabled = false;
    uploadBtn.textContent = "Upload PDF";
  }
}

async function createNewChat() {
  state.isSending = true;
  updateSendState();
  try {
    const resp = await fetch("/api/chat/new", { method: "POST" });
    const data = await resp.json();
    state.conversationId = data.conversation_id || "";
    state.messages = [];

    if (state.conversationId) {
      upsertThread({
        id: state.conversationId,
        title: "New legal chat",
        preview: "No messages yet",
        updatedAt: new Date().toISOString(),
      });
    }
  } catch (err) {
    console.warn("Could not create new server chat", err);
    state.conversationId = "";
    state.messages = [];
  } finally {
    state.isSending = false;
    updateSendState();
  }

  renderMessages();
  renderThreadList();
  setHeaderFromThread();
  resetInsights();
  composerInput.value = "";
  updateComposerMeta();
  autoResizeComposer();
  composerInput.focus();
}

async function loadConversation(conversationId) {
  if (!conversationId) {
    return;
  }

  try {
    const resp = await fetch(`/api/chat/${encodeURIComponent(conversationId)}`);
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || data.error || "Could not load chat");
    }

    state.conversationId = conversationId;
    state.messages = (data.messages || []).map((message) => ({
      role: message.role,
      content: message.content,
      meta: message.meta || {},
    }));

    const lastAssistant = [...state.messages].reverse().find((message) => message.role === "assistant");
    const meta = lastAssistant?.meta || {};
    domainBadge.textContent = `domain: ${meta.domain || "-"}`;
    domainBadge.classList.toggle("muted", !meta.domain);
    languageBadge.textContent = `language: ${languageLabel(meta.language)}`;
    languageBadge.classList.toggle("muted", !meta.language);
    contextNoticeEl.textContent = meta.context_notice || "Source: -";
    renderCitations(meta.citations || []);
    renderLiveSources(meta.live_sources || []);
  } catch (err) {
    console.warn("Could not load chat thread", err);
  }

  renderMessages();
  renderThreadList();
  setHeaderFromThread();
}

function updateThreadAfterResponse(question, answer, language, domain) {
  if (!state.conversationId) {
    return;
  }
  const existing = state.threads.find((item) => item.id === state.conversationId);
  const title = existing?.title && existing.title !== "New legal chat" ? existing.title : summarizeTitle(question);
  upsertThread({
    id: state.conversationId,
    title,
    preview: summarizeTitle(answer),
    updatedAt: new Date().toISOString(),
    language,
    domain,
  });
  setHeaderFromThread();
}

async function sendQuestion() {
  const question = composerInput.value.trim();
  if (!question) {
    composerInput.focus();
    return;
  }

  appendMessage("user", question);
  composerInput.value = "";
  updateComposerMeta();
  autoResizeComposer();
  state.isSending = true;
  updateSendState();
  sendBtn.textContent = "Thinking...";
  appendMessage("assistant", "", { isTyping: true });

  try {
    const resp = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        language: detectInputLanguage(question),
        conversation_id: state.conversationId,
      }),
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || data.error || "Request failed");
    }

    state.conversationId = data.conversation_id || state.conversationId;
    removeTypingMessage();
    appendMessage("assistant", data.answer || "No answer generated.");

    domainBadge.textContent = `domain: ${data.domain || "-"}`;
    domainBadge.classList.remove("muted");
    languageBadge.textContent = `language: ${languageLabel(data.language)}`;
    languageBadge.classList.remove("muted");
    contextNoticeEl.textContent = data.context_notice || `Source: ${data.context_source_label || "-"}`;

    renderCitations(data.citations || []);
    renderLiveSources(data.live_sources || []);
    updateThreadAfterResponse(question, data.answer || "", data.language, data.domain);
  } catch (err) {
    removeTypingMessage();
    appendMessage("assistant", `Error: ${err.message}`);
    contextNoticeEl.textContent = "Source: -";
  } finally {
    state.isSending = false;
    updateSendState();
    sendBtn.textContent = "Send";
  }
}

function bindEvents() {
  sendBtn.addEventListener("click", sendQuestion);
  newChatBtn.addEventListener("click", createNewChat);
  themeToggleBtn.addEventListener("click", toggleTheme);
  insightsToggleBtn.addEventListener("click", toggleInsights);
  insightsHeadToggleBtn.addEventListener("click", () => setInsightsOpen(false));
  uploadBtn.addEventListener("click", uploadPdf);

  composerInput.addEventListener("keydown", (event) => {
    if (!event.shiftKey && event.key === "Enter") {
      event.preventDefault();
      sendQuestion();
    }
  });

  composerInput.addEventListener("input", () => {
    updateComposerMeta();
    autoResizeComposer();
    updateSendState();
  });

  threadListEl.addEventListener("click", (event) => {
    const deleteBtn = event.target.closest("[data-delete-thread-id]");
    if (deleteBtn) {
      const deleteId = deleteBtn.getAttribute("data-delete-thread-id");
      deleteThread(deleteId);
      return;
    }

    const target = event.target.closest("[data-thread-id]");
    if (!target) {
      return;
    }
    const threadId = target.getAttribute("data-thread-id");
    loadConversation(threadId);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.insightsOpen) {
      setInsightsOpen(false);
    }
  });
}

async function boot() {
  loadTheme();
  fetchHealth();
  state.threads = loadThreads();
  bindCollapsibles();
  renderThreadList();
  renderMessages();
  resetInsights();
  setInsightsOpen(false);
  updateComposerMeta();
  autoResizeComposer();
  updateSendState();

  bindEvents();
  fetchSources();
  fetchDomains();

  if (state.threads.length) {
    await loadConversation(state.threads[0].id);
  } else {
    await createNewChat();
  }
}

boot();
