import {
  APIError,
  createChatSession,
  listChatSessions,
  getChatMessages,
  sendChatMessage,
  listDocuments,
  getChatDocuments,
  setChatDocuments,
} from "../../components/api_client.js";
import { clearSession, getSession } from "../../components/session.js";

// ── Auth guard ────────────────────────────────────────────────────────────────
const session = getSession();
if (!session?.accessToken) {
  window.location.replace("./login.html");
  throw new Error("unauthenticated");
}

const { user } = session;

// ── Token accessor — always reads current value (may be refreshed in background) ──
function getToken() {
  const s = getSession();
  return s?.accessToken || null;
}

// ── Topbar ────────────────────────────────────────────────────────────────────
const _displayName = user?.username || user?.email || "";
const _avatarEl = document.querySelector("[data-user-slot]");
if (_avatarEl) {
  _avatarEl.textContent = _displayName.charAt(0).toUpperCase();
  _avatarEl.title = _displayName;
}
document.querySelector("[data-signout]").addEventListener("click", () => {
  clearSession();
  window.location.replace("./login.html");
});

// ── DOM refs ──────────────────────────────────────────────────────────────────
const newChatBtn       = document.getElementById("new-chat-btn");
const sessionListEl    = document.getElementById("session-list");
const chatMessagesEl   = document.getElementById("chat-messages");
const chatPlaceholder  = document.getElementById("chat-placeholder");
const typingIndicator  = document.getElementById("typing-indicator");
const chatInput        = document.getElementById("chat-input");
const sendBtn          = document.getElementById("send-btn");

// Doc picker DOM refs
const docsContextStrip  = document.getElementById("docs-context-strip");
const docsContextLabel  = document.getElementById("docs-context-label");
const docsSelectBtn     = document.getElementById("docs-select-btn");
const docPickerOverlay  = document.getElementById("doc-picker-overlay");
const docPickerList     = document.getElementById("doc-picker-list");
const docPickerClose    = document.getElementById("doc-picker-close");
const docPickerClear    = document.getElementById("doc-picker-clear");
const docPickerSave     = document.getElementById("doc-picker-save");

// ── State ───────────────────────────────────────────────────────────────
let activeChatId  = null;
let isSending     = false;
let activeDocSelection = []; // [{id, title, source_type, filename}] for current chat

// ── Session list ──────────────────────────────────────────────────────────────
async function loadSessions() {
  sessionListEl.innerHTML =
    '<p style="padding:10px 12px;color:var(--muted);font-size:0.88rem;">Loading…</p>';
  try {
    const resp = await listChatSessions(getToken());
    const sessions = Array.isArray(resp) ? resp : [];
    renderSessionList(sessions);
  } catch (err) {
    sessionListEl.innerHTML =
      `<p style="padding:10px 12px;color:#a13716;font-size:0.86rem;">${
        err instanceof APIError ? err.message : "Failed to load sessions."
      }</p>`;
  }
}

function renderSessionList(sessions) {
  sessionListEl.innerHTML = "";
  if (!sessions.length) {
    sessionListEl.innerHTML =
      '<p style="padding:10px 12px;color:var(--muted);font-size:0.86rem;">No chats yet. Click + New to start.</p>';
    return;
  }
  sessions.forEach((s) => {
    const btn = buildSessionButton(s);
    sessionListEl.appendChild(btn);
  });
}

function buildSessionButton(session) {
  const btn = document.createElement("button");
  btn.className = "session-item";
  btn.dataset.chatId = session.id;
  if (session.id === activeChatId) btn.classList.add("active");

  const date = new Date(session.updated_at).toLocaleDateString();
  btn.innerHTML = `
    ${escHtml(session.title)}
    <span class="session-item-meta">${date}</span>
  `.trim();

  btn.addEventListener("click", () => switchSession(session.id));
  return btn;
}

function prependSessionToList(session) {
  // Remove existing button if present (update)
  const existing = sessionListEl.querySelector(`[data-chat-id="${session.id}"]`);
  if (existing) existing.remove();

  // Remove placeholder message if present
  const placeholder = sessionListEl.querySelector("p");
  if (placeholder) placeholder.remove();

  const btn = buildSessionButton(session);
  sessionListEl.prepend(btn);
}

function setActiveSessionButton(chatId) {
  sessionListEl.querySelectorAll(".session-item").forEach((b) => {
    b.classList.toggle("active", b.dataset.chatId === chatId);
  });
}

// ── Switch session ────────────────────────────────────────────────────────────
async function switchSession(chatId) {
  if (isSending) return;
  activeChatId = chatId;
  activeDocSelection = [];
  setActiveSessionButton(chatId);
  enableInput(false);
  clearMessages();
  showPlaceholder(false);

  appendLoadingBubble("Loading messages…");

  try {
    // Load messages and document selection in parallel
    const [msgResp, docResp] = await Promise.all([
      getChatMessages(getToken(), chatId),
      getChatDocuments(getToken(), chatId).catch(() => ({ documents: [] })),
    ]);
    const messages = Array.isArray(msgResp) ? msgResp : [];
    activeDocSelection = docResp?.documents || [];
    updateDocsContextStrip();
    clearMessages();
    if (!messages.length) {
      showPlaceholder(true, "New chat", "Ask your first question below.");
    } else {
      messages.forEach((m) => appendMessage(m));
      scrollToBottom();
    }
  } catch (err) {
    clearMessages();
    appendError(err instanceof APIError ? err.message : "Failed to load messages.");
  } finally {
    enableInput(true);
  }
}

// ── New chat ──────────────────────────────────────────────────────────────────
newChatBtn.addEventListener("click", async () => {
  newChatBtn.disabled = true;
  try {
    const chat = await createChatSession(getToken(), "New Chat");
    prependSessionToList(chat);
    await switchSession(chat.id);
  } catch (err) {
    window.alert(err instanceof APIError ? err.message : "Failed to create chat.");
  } finally {
    newChatBtn.disabled = false;
  }
});

// ── Send message ──────────────────────────────────────────────────────────────
async function submitMessage() {
  if (!activeChatId || isSending) return;
  const content = chatInput.value.trim();
  if (!content) return;

  isSending = true;
  enableInput(false);
  chatInput.value = "";

  // Optimistically render user bubble
  appendMessage({ role: "user", content, created_at: new Date().toISOString() });
  scrollToBottom();

  typingIndicator.hidden = false;
  scrollToBottom();

  try {
    const result = await sendChatMessage(getToken(), activeChatId, content);
    typingIndicator.hidden = true;

    if (result.out_of_context) {
      // Document doesn't cover this question — show choice card
      appendOutOfContextCard(content, result.assistant_message, result.router);
    } else {
      appendMessage(result.assistant_message, result.router);
    }

    // Update session title in sidebar (auto-titled after first message)
    const sessResp = await listChatSessions(getToken());
    const sessions = Array.isArray(sessResp) ? sessResp : [];
    const updated = sessions.find((s) => s.id === activeChatId);
    if (updated) prependSessionToList(updated);
    setActiveSessionButton(activeChatId);
  } catch (err) {
    typingIndicator.hidden = true;
    appendError(err instanceof APIError ? err.message : "Failed to send message.");
  } finally {
    isSending = false;
    enableInput(true);
    chatInput.focus();
    scrollToBottom();
  }
}

sendBtn.addEventListener("click", submitMessage);

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitMessage();
  }
});

// Auto-grow textarea
chatInput.addEventListener("input", () => {
  chatInput.style.height = "auto";
  chatInput.style.height = Math.min(chatInput.scrollHeight, 160) + "px";
});

// ── Out-of-context card ───────────────────────────────────────────────────────

function appendOutOfContextCard(originalQuestion, msg, router) {
  // First render the assistant's "not found" message as a normal bubble
  appendMessage(msg, router);

  // Then attach a choice card beneath it
  const card = document.createElement("div");
  card.className = "ooc-card";
  card.innerHTML = `
    <p class="ooc-card-prompt">Would you like me to answer from my general knowledge?</p>
    <div class="ooc-card-actions">
      <button type="button" class="button button-solid ooc-yes-btn">Yes, use general knowledge</button>
      <button type="button" class="button button-ghost ooc-no-btn">No, thanks</button>
    </div>
  `.trim();

  card.querySelector(".ooc-no-btn").addEventListener("click", () => card.remove());

  card.querySelector(".ooc-yes-btn").addEventListener("click", async () => {
    card.remove();
    await sendAsGeneralKnowledge(originalQuestion);
  });

  chatMessagesEl.appendChild(card);
  scrollToBottom();
}

async function sendAsGeneralKnowledge(question) {
  if (!activeChatId || isSending) return;
  isSending = true;
  enableInput(false);

  typingIndicator.hidden = false;
  scrollToBottom();

  try {
    const result = await sendChatMessage(getToken(), activeChatId, question, true);
    typingIndicator.hidden = true;
    appendMessage(result.assistant_message, result.router);
  } catch (err) {
    typingIndicator.hidden = true;
    appendError(err instanceof APIError ? err.message : "Failed to get general knowledge answer.");
  } finally {
    isSending = false;
    enableInput(true);
    scrollToBottom();
  }
}

// ── Markdown renderer (marked.js loaded via CDN in chat.html) ────────────────
function renderMarkdown(text) {
  if (typeof marked !== "undefined") {
    return marked.parse(text, { breaks: true, gfm: true });
  }
  // Fallback: escape HTML and preserve newlines
  return escHtml(text).replace(/\n/g, "<br>");
}

// ── Render helpers ────────────────────────────────────────────────────────────
function appendMessage(msg, router = null) {
  chatPlaceholder.hidden = true;

  const wrap = document.createElement("div");
  wrap.className = `message-bubble ${msg.role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble-content";
  if (msg.role === "assistant") {
    bubble.innerHTML = renderMarkdown(msg.content);
  } else {
    bubble.textContent = msg.content;
  }
  wrap.appendChild(bubble);

  // Meta line
  const meta = document.createElement("div");
  meta.className = "bubble-meta";
  const timeStr = new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  let metaText = timeStr;
  if (msg.role === "assistant" && msg.model_used) {
    metaText += ` · ${msg.model_used}`;
  }
  if (router && msg.role === "assistant") {
    metaText += ` · via ${router.category || "general"}`;
  }
  meta.textContent = metaText;
  wrap.appendChild(meta);

  // Citations
  if (msg.role === "assistant" && msg.sources && msg.sources.length > 0) {
    const citBlock = buildCitations(msg.sources);
    wrap.appendChild(citBlock);
  }

  chatMessagesEl.appendChild(wrap);
}

function buildCitations(sources) {
  const wrap = document.createElement("div");
  wrap.className = "citations";

  // Toggle button (collapsed by default)
  const toggle = document.createElement("button");
  toggle.className = "citations-toggle";
  toggle.type = "button";
  toggle.innerHTML = `<span class="citations-arrow">&#9654;</span> Sources (${sources.length})`;

  // Items container — hidden by default
  const body = document.createElement("div");
  body.className = "citations-body";
  body.hidden = true;

  toggle.addEventListener("click", () => {
    const open = !body.hidden;
    body.hidden = open;
    toggle.querySelector(".citations-arrow").style.transform = open ? "" : "rotate(90deg)";
  });

  wrap.appendChild(toggle);

  sources.forEach((src, i) => {
    const item = document.createElement("div");
    item.className = "citation-item";
    const score = src.similarity_score ? ` · ${(src.similarity_score * 100).toFixed(0)}% match` : "";
    item.innerHTML = `
      <strong>Source ${i + 1}${score}</strong>
      ${src.snippet ? `<div class="citation-snippet">${escHtml(src.snippet)}</div>` : ""}
    `.trim();
    body.appendChild(item);
  });

  wrap.appendChild(body);
  return wrap;
}

function appendLoadingBubble(text) {
  chatPlaceholder.hidden = true;
  const p = document.createElement("p");
  p.id = "loading-bubble";
  p.style.cssText = "color:var(--muted);font-size:0.9rem;padding:8px 0;";
  p.textContent = text;
  chatMessagesEl.appendChild(p);
}

function appendError(message) {
  const p = document.createElement("p");
  p.style.cssText = "color:#a13716;font-size:0.9rem;padding:6px 0;";
  p.textContent = `Error: ${message}`;
  chatMessagesEl.appendChild(p);
}

function clearMessages() {
  chatMessagesEl.innerHTML = "";
  chatMessagesEl.appendChild(chatPlaceholder);
  chatPlaceholder.hidden = true;
}

function showPlaceholder(show, heading = "Select or start a chat", body = "Pick a session from the sidebar, or click + New to begin.") {
  chatPlaceholder.hidden = !show;
  if (show) {
    chatPlaceholder.querySelector("h3").textContent = heading;
    chatPlaceholder.querySelector("p").textContent = body;
  }
}

function enableInput(enabled) {
  chatInput.disabled = !enabled || !activeChatId;
  sendBtn.disabled   = !enabled || !activeChatId;
  if (docsContextStrip) docsContextStrip.hidden = !activeChatId;
}

// ── Document context strip ────────────────────────────────────────────────────

function updateDocsContextStrip() {
  if (!activeChatId) return;
  if (!docsContextStrip) return;
  docsContextStrip.hidden = false;
  if (!activeDocSelection || activeDocSelection.length === 0) {
    docsContextLabel.textContent = "All documents";
  } else if (activeDocSelection.length === 1) {
    docsContextLabel.textContent = activeDocSelection[0].title || "1 document";
  } else {
    docsContextLabel.textContent = `${activeDocSelection.length} documents`;
  }
}

// ── Document picker ───────────────────────────────────────────────────────────

// IDs checked in the picker modal (may differ from activeDocSelection until saved)
let pendingDocIds = new Set();

async function openDocPicker() {
  if (!activeChatId) return;
  // Seed pending state from current selection
  pendingDocIds = new Set(activeDocSelection.map((d) => d.id));

  docPickerList.innerHTML =
    '<p style="color:var(--muted);font-size:0.9rem;">Loading…</p>';
  docPickerOverlay.hidden = false;
  document.body.style.overflow = "hidden";

  try {
    const resp = await listDocuments(getToken());
    const docs = Array.isArray(resp)
      ? resp
      : Array.isArray(resp?.documents)
      ? resp.documents
      : [];

    if (!docs.length) {
      docPickerList.innerHTML =
        '<p style="color:var(--muted);font-size:0.9rem;">No documents uploaded yet.</p>';
      return;
    }

    docPickerList.innerHTML = "";
    docs.forEach((doc) => {
      const item = document.createElement("label");
      item.className = "doc-picker-item";
      item.htmlFor = `dp-${doc.id}`;

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = `dp-${doc.id}`;
      cb.value = doc.id;
      cb.checked = pendingDocIds.has(doc.id);
      cb.addEventListener("change", () => {
        if (cb.checked) {
          pendingDocIds.add(doc.id);
        } else {
          pendingDocIds.delete(doc.id);
        }
      });

      const meta = document.createElement("div");
      meta.className = "doc-picker-item-meta";
      meta.innerHTML = `
        <span class="doc-picker-item-title">${escHtml(doc.title || "Untitled")}</span>
        <span class="doc-picker-item-type">${escHtml(doc.source_type || "")}</span>
      `.trim();

      item.appendChild(cb);
      item.appendChild(meta);
      docPickerList.appendChild(item);
    });
  } catch (err) {
    docPickerList.innerHTML = `<p style="color:#a13716;font-size:0.9rem;">Error loading documents: ${
      err instanceof APIError ? err.message : "unknown error"
    }</p>`;
  }
}

function closeDocPicker() {
  docPickerOverlay.hidden = true;
  document.body.style.overflow = "";
}

async function saveDocSelection() {
  const ids = [...pendingDocIds];
  docPickerSave.disabled = true;
  try {
    const resp = await setChatDocuments(getToken(), activeChatId, ids);
    // Rebuild activeDocSelection from the picker's checked items
    const allCheckboxes = docPickerList.querySelectorAll("input[type=checkbox]");
    activeDocSelection = [];
    allCheckboxes.forEach((cb) => {
      if (cb.checked) {
        const label = cb.closest("label");
        const title = label?.querySelector(".doc-picker-item-title")?.textContent || cb.value;
        activeDocSelection.push({ id: cb.value, title });
      }
    });
    updateDocsContextStrip();
    closeDocPicker();
  } catch (err) {
    window.alert(
      "Failed to save document selection: " +
        (err instanceof APIError ? err.message : "unknown error")
    );
  } finally {
    docPickerSave.disabled = false;
  }
}

// Event listeners for picker
if (docsSelectBtn)  docsSelectBtn.addEventListener("click", openDocPicker);
if (docPickerClose) docPickerClose.addEventListener("click", closeDocPicker);
if (docPickerSave)  docPickerSave.addEventListener("click", saveDocSelection);
if (docPickerClear) {
  docPickerClear.addEventListener("click", () => {
    pendingDocIds.clear();
    docPickerList.querySelectorAll("input[type=checkbox]").forEach((cb) => {
      cb.checked = false;
    });
  });
}
// Close on overlay backdrop click
if (docPickerOverlay) {
  docPickerOverlay.addEventListener("click", (e) => {
    if (e.target === docPickerOverlay) closeDocPicker();
  });
}

function scrollToBottom() {
  window.requestAnimationFrame(() => {
    chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Initialise ────────────────────────────────────────────────────────────────
loadSessions();
