import {
  APIError,
  uploadDocument,
  addTextDocument,
  listDocuments,
  deleteDocument,
  getIngestionStatus,
  retryIngestion,
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
const dropZone       = document.getElementById("drop-zone");
const fileInput      = document.getElementById("file-input");
const selectedName   = document.getElementById("selected-file-name");
const uploadTitle    = document.getElementById("upload-title");
const uploadBtn      = document.getElementById("upload-btn");
const uploadStatus   = document.getElementById("upload-status");
const progressWrap   = document.getElementById("upload-progress-wrap");
const progressBar    = document.getElementById("upload-progress-bar");

const textTitle      = document.getElementById("text-title");
const textContent    = document.getElementById("text-content");
const textSubmitBtn  = document.getElementById("text-submit-btn");
const textStatus     = document.getElementById("text-status");

const docList        = document.getElementById("doc-list");
const refreshDocsBtn = document.getElementById("refresh-docs-btn");

// ── Polling registry ──────────────────────────────────────────────────────────
// Map<docId, intervalId>
const pollingMap = new Map();

function startPolling(docId, ingestionId, badgeEl) {
  if (pollingMap.has(docId)) return;
  const id = window.setInterval(async () => {
    try {
      const res = await getIngestionStatus(getToken(), docId, ingestionId);
      const status = res.status;
      updateBadge(badgeEl, status);
      if (status === "ready" || status === "failed") {
        window.clearInterval(pollingMap.get(docId));
        pollingMap.delete(docId);
        if (status === "failed") {
          // Add retry button next to the badge (actionsEl = badge's parent)
          const actionsEl = badgeEl.parentElement;
          if (actionsEl) addRetryButton(docId, badgeEl, actionsEl);
        }
      }
    } catch (_) {
      // silently retry
    }
  }, 3000);
  pollingMap.set(docId, id);
}

function updateBadge(el, status) {
  el.className = "badge";
  if (status === "ready")                           el.classList.add("badge-ready");
  else if (status === "failed" || status === "no-ingestion") el.classList.add("badge-failed");
  else                                              el.classList.add("badge-processing");
  el.textContent = status;
}

// ── Status line helper ────────────────────────────────────────────────────────
function setStatus(el, message, type = "") {
  el.textContent = message;
  el.className = "status-line" + (type ? ` ${type}` : "");
}

// ── Upload progress animation (fake) ─────────────────────────────────────────
function animateProgress(start, end, durationMs) {
  progressWrap.hidden = false;
  progressBar.style.width = start + "%";
  let startTime = null;
  function step(ts) {
    if (!startTime) startTime = ts;
    const pct = Math.min(start + ((end - start) * (ts - startTime)) / durationMs, end);
    progressBar.style.width = pct + "%";
    if (pct < end) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function resetProgress() {
  progressBar.style.width = "0%";
  progressWrap.hidden = true;
}

// ── Drop zone ─────────────────────────────────────────────────────────────────
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});

dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer?.files?.[0];
  if (file) onFileSelected(file);
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files?.[0];
  if (file) onFileSelected(file);
});

let selectedFile = null;

function onFileSelected(file) {
  selectedFile = file;
  selectedName.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  uploadBtn.disabled = false;
  setStatus(uploadStatus, "");
  resetProgress();
}

// ── Upload submit ─────────────────────────────────────────────────────────────
uploadBtn.addEventListener("click", async () => {
  if (!selectedFile) return;

  uploadBtn.disabled = true;
  setStatus(uploadStatus, "Uploading…");
  animateProgress(0, 70, 1200);

  const fd = new FormData();
  fd.append("file", selectedFile);
  const titleVal = uploadTitle.value.trim();
  if (titleVal) fd.append("title", titleVal);

  try {
    const res = await uploadDocument(getToken(), fd);
    animateProgress(70, 100, 400);
    window.setTimeout(() => {
      resetProgress();
      selectedFile = null;
      selectedName.textContent = "";
      fileInput.value = "";
      uploadTitle.value = "";
      uploadBtn.disabled = true;
      setStatus(uploadStatus, "Done — document added.", "ok");
      refreshDocList();
    }, 450);
  } catch (err) {
    resetProgress();
    uploadBtn.disabled = false;
    setStatus(uploadStatus, err instanceof APIError ? err.message : "Upload failed.", "err");
  }
});

// ── Text submit ───────────────────────────────────────────────────────────────
textSubmitBtn.addEventListener("click", async () => {
  const title = textTitle.value.trim();
  const text  = textContent.value.trim();

  if (!title) { setStatus(textStatus, "Title is required.", "err"); return; }
  if (!text)  { setStatus(textStatus, "Content is required.", "err"); return; }

  textSubmitBtn.disabled = true;
  setStatus(textStatus, "Saving…");

  try {
    await addTextDocument(getToken(), title, text);
    textTitle.value = "";
    textContent.value = "";
    setStatus(textStatus, "Text context added.", "ok");
    refreshDocList();
  } catch (err) {
    setStatus(textStatus, err instanceof APIError ? err.message : "Failed to add text.", "err");
  } finally {
    textSubmitBtn.disabled = false;
  }
});

// ── Document list ─────────────────────────────────────────────────────────────
async function refreshDocList() {
  docList.innerHTML = '<p class="empty-state">Loading…</p>';

  try {
    const res = await listDocuments(getToken());
    const docs = res.documents || [];
    if (!docs.length) {
      docList.innerHTML = '<p class="empty-state">No documents yet. Upload a file or add text context above.</p>';
      return;
    }
    renderDocList(docs);
  } catch (err) {
    docList.innerHTML = `<p class="empty-state" style="color:#a13716">${
      err instanceof APIError ? err.message : "Failed to load documents."
    }</p>`;
  }
}

function renderDocList(docs) {
  docList.innerHTML = "";
  docs.forEach((doc) => {
    const item = document.createElement("div");
    item.className = "doc-item";
    item.dataset.docId = doc.id;

    const sourceLabel = doc.source_type === "upload" ? "PDF / File" : "Text";
    const date = new Date(doc.created_at).toLocaleDateString();

    const badgeEl = document.createElement("span");
    badgeEl.className = "badge badge-processing";
    badgeEl.textContent = "unknown";

    item.innerHTML = `
      <div class="doc-item-info" style="flex:1;min-width:0;">
        <div class="doc-item-title" title="${escHtml(doc.title)}">${escHtml(doc.title)}</div>
        <div class="doc-item-meta">${sourceLabel} · Added ${date}</div>
      </div>
      <div class="doc-item-actions"></div>
    `.trim();

    const actionsEl = item.querySelector(".doc-item-actions");
    actionsEl.appendChild(badgeEl);

    const delBtn = document.createElement("button");
    delBtn.className = "button button-danger";
    delBtn.style.cssText = "padding:0.36rem 0.78rem;font-size:0.84rem;border-radius:8px;";
    delBtn.textContent = "Delete";
    delBtn.addEventListener("click", () => confirmDelete(doc.id, doc.title));
    actionsEl.appendChild(delBtn);

    docList.appendChild(item);

    // Resolve ingestion status
    resolveIngestionStatus(doc, badgeEl, actionsEl);
  });
}

async function resolveIngestionStatus(doc, badgeEl, actionsEl) {
  const ingestionId = doc.current_ingestion_id;
  if (!ingestionId) {
    updateBadge(badgeEl, "no-ingestion");
    addRetryButton(doc.id, badgeEl, actionsEl);
    return;
  }
  try {
    const res = await getIngestionStatus(getToken(), doc.id, ingestionId);
    updateBadge(badgeEl, res.status);
    if (res.status === "processing") {
      startPolling(doc.id, ingestionId, badgeEl);
    } else if (res.status === "failed") {
      addRetryButton(doc.id, badgeEl, actionsEl);
    }
  } catch (_) {
    updateBadge(badgeEl, "unknown");
  }
}

function addRetryButton(docId, badgeEl, actionsEl) {
  // Avoid duplicate retry buttons
  if (actionsEl.querySelector(".retry-btn")) return;
  const btn = document.createElement("button");
  btn.className = "button retry-btn";
  btn.style.cssText = "padding:0.36rem 0.78rem;font-size:0.84rem;border-radius:8px;background:rgba(15,118,110,0.12);color:var(--brand-deep);border:1px solid rgba(15,118,110,0.3);cursor:pointer;";
  btn.textContent = "Retry";
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Retrying…";
    updateBadge(badgeEl, "processing");
    try {
      const res = await retryIngestion(getToken(), docId);
      const newIngestionId = res.ingestion?.id;
      if (newIngestionId) {
        startPolling(docId, newIngestionId, badgeEl);
        // Remove retry button — polling will show final status
        btn.remove();
      } else {
        updateBadge(badgeEl, "failed");
        btn.disabled = false;
        btn.textContent = "Retry";
      }
    } catch (err) {
      updateBadge(badgeEl, "failed");
      btn.disabled = false;
      btn.textContent = "Retry";
      window.alert(
        "Re-ingestion failed: " +
          (err instanceof APIError ? err.message : "unknown error")
      );
    }
  });
  // Insert retry button before the delete button
  const delBtn = actionsEl.querySelector(".button-danger");
  actionsEl.insertBefore(btn, delBtn);
}

async function confirmDelete(docId, title) {
  if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return;
  try {
    await deleteDocument(getToken(), docId);
    // Stop any active poll for this doc
    if (pollingMap.has(docId)) {
      window.clearInterval(pollingMap.get(docId));
      pollingMap.delete(docId);
    }
    refreshDocList();
  } catch (err) {
    window.alert(err instanceof APIError ? err.message : "Delete failed.");
  }
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
refreshDocsBtn.addEventListener("click", refreshDocList);
refreshDocList();
