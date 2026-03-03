const DEFAULT_API_BASE_URL = "http://localhost:5000";

function normalizeBaseUrl(url) {
  return (url || DEFAULT_API_BASE_URL).replace(/\/+$/, "");
}

function resolveApiBaseUrl() {
  if (
    window.TUTOR_BOT_CONFIG &&
    typeof window.TUTOR_BOT_CONFIG.API_BASE_URL === "string"
  ) {
    return normalizeBaseUrl(window.TUTOR_BOT_CONFIG.API_BASE_URL);
  }
  return DEFAULT_API_BASE_URL;
}

const API_BASE_URL = resolveApiBaseUrl();

export class APIError extends Error {
  constructor(message, statusCode = 0, details = null) {
    super(message);
    this.name = "APIError";
    this.statusCode = statusCode;
    this.details = details;
  }
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

// ── Token refresh helpers (read/write localStorage directly to avoid circular import) ──
const _SESSION_KEY = "tutorbot.session.v1";

function _readSession() {
  try { return JSON.parse(localStorage.getItem(_SESSION_KEY) || "null"); } catch { return null; }
}

function _writeAccessToken(newAccessToken) {
  const s = _readSession();
  if (!s) return;
  s.accessToken = newAccessToken;
  localStorage.setItem(_SESSION_KEY, JSON.stringify(s));
}

async function _refreshAccessToken() {
  const s = _readSession();
  const rt = s?.refreshToken;
  if (!rt) return null;

  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { Authorization: `Bearer ${rt}`, Accept: "application/json" },
    });
    if (!res.ok) return null;
    const data = await res.json();
    const at = data.access_token;
    if (!at) return null;
    _writeAccessToken(at);
    return at;
  } catch {
    return null;
  }
}

async function request(
  path,
  {
    method = "GET",
    token = null,
    payload,
    params = null,
    timeoutMs = 10000,
    _isRetry = false,
  } = {},
) {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (params && typeof params === "object") {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const headers = {
    Accept: "application/json",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (payload !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  let response;
  try {
    response = await fetch(url.toString(), {
      method,
      headers,
      body: payload === undefined ? undefined : JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new APIError("request timed out", 0);
    }
    throw new APIError("network error: unable to reach backend", 0);
  } finally {
    window.clearTimeout(timeoutId);
  }

  const contentType = response.headers.get("content-type") || "";
  let body = null;

  if (contentType.includes("application/json")) {
    body = await response.json().catch(() => null);
  } else {
    const text = await response.text().catch(() => "");
    body = text ? { error: text } : null;
  }

  if (!response.ok) {
    // On 401, try refreshing the access token once then retry the original request.
    if (response.status === 401 && token && !_isRetry) {
      const newToken = await _refreshAccessToken();
      if (newToken) {
        return request(path, { method, token: newToken, payload, params, timeoutMs, _isRetry: true });
      }
      // Refresh failed — clear session and redirect to login.
      localStorage.removeItem(_SESSION_KEY);
      window.location.replace("/pages/login.html");
      throw new APIError("session expired — please sign in again", 401);
    }

    const message =
      (body && (body.error || body.message)) ||
      `request failed with status ${response.status}`;
    throw new APIError(message, response.status, body);
  }

  return body || {};
}

export function register(email, password, username = null) {
  return request("/api/auth/register", {
    method: "POST",
    payload: { email, password, username },
  });
}

export function login(email, password) {
  return request("/api/auth/login", {
    method: "POST",
    payload: { email, password },
  });
}

export function refreshToken(refreshTokenValue) {
  return request("/api/auth/refresh", {
    method: "POST",
    token: refreshTokenValue,
  });
}

export function getMe(accessToken) {
  return request("/api/auth/me", {
    method: "GET",
    token: accessToken,
  });
}

export function authedGet(path, accessToken, params = null) {
  return request(path, {
    method: "GET",
    token: accessToken,
    params,
    timeoutMs: 30000,
  });
}

export function authedPost(path, accessToken, payload) {
  return request(path, {
    method: "POST",
    token: accessToken,
    payload,
    timeoutMs: 30000,
  });
}

export function authedDelete(path, accessToken) {
  return request(path, {
    method: "DELETE",
    token: accessToken,
  });
}

// ── Documents ─────────────────────────────────────────────────────────────────

/**
 * Upload a PDF or text file (multipart/form-data).
 * @param {string} accessToken
 * @param {FormData} formData  – must include a `file` field (and optionally `title`)
 */
export async function uploadDocument(accessToken, formData) {
  const doUpload = async (token) => {
    const url = `${API_BASE_URL}/api/documents/upload`;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 60000);

    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
        signal: controller.signal,
      });
    } catch (err) {
      if (err.name === "AbortError") throw new APIError("upload timed out", 0);
      throw new APIError("network error: unable to reach backend", 0);
    } finally {
      window.clearTimeout(timeoutId);
    }
    return response;
  };

  let response = await doUpload(accessToken);

  if (response.status === 401) {
    const newToken = await _refreshAccessToken();
    if (newToken) {
      response = await doUpload(newToken);
    } else {
      localStorage.removeItem(_SESSION_KEY);
      window.location.replace("/pages/login.html");
      throw new APIError("session expired — please sign in again", 401);
    }
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = (body && (body.error || body.message)) || `upload failed (${response.status})`;
    throw new APIError(message, response.status, body);
  }
  return body || {};
}

/** POST /api/documents/text — add plain-text context */
export function addTextDocument(accessToken, title, text) {
  return request("/api/documents/text", {
    method: "POST",
    token: accessToken,
    payload: { title, text },
    timeoutMs: 60000,
  });
}

/** GET /api/documents — list user's documents */
export function listDocuments(accessToken) {
  return authedGet("/api/documents", accessToken);
}

/** GET /api/documents/<id> — document detail */
export function getDocument(accessToken, docId) {
  return authedGet(`/api/documents/${docId}`, accessToken);
}

/** DELETE /api/documents/<id> — soft delete */
export function deleteDocument(accessToken, docId) {
  return authedDelete(`/api/documents/${docId}`, accessToken);
}

/** GET /api/documents/<id>/ingestions/<ingestionId>/status */
export function getIngestionStatus(accessToken, docId, ingestionId) {
  return authedGet(`/api/documents/${docId}/ingestions/${ingestionId}/status`, accessToken);
}

/** POST /api/documents/<id>/reingest — retry a failed ingestion */
export function retryIngestion(accessToken, docId) {
  return request(`/api/documents/${docId}/reingest`, {
    method: "POST",
    token: accessToken,
    timeoutMs: 120000,
  });
}

// ── Chat ──────────────────────────────────────────────────────────────────────

/** POST /api/chat/sessions — create a new chat session */
export function createChatSession(accessToken, title = "New Chat") {
  return request("/api/chat/sessions", {
    method: "POST",
    token: accessToken,
    payload: { title },
  });
}

/** GET /api/chat/sessions — list sessions (newest first) */
export function listChatSessions(accessToken) {
  return authedGet("/api/chat/sessions", accessToken);
}

/** GET /api/chat/sessions/<id>/messages */
export function getChatMessages(accessToken, chatId) {
  return authedGet(`/api/chat/sessions/${chatId}/messages`, accessToken);
}

/** POST /api/chat/sessions/<id>/messages — send user message, receive AI answer */
export function sendChatMessage(accessToken, chatId, content, useGeneralKnowledge = false) {
  const payload = { content };
  if (useGeneralKnowledge) payload.use_general_knowledge = true;
  return request(`/api/chat/sessions/${chatId}/messages`, {
    method: "POST",
    token: accessToken,
    payload,
    timeoutMs: 120000,
  });
}

/** GET /api/chat/sessions/<id>/documents — get the documents pinned to a chat */
export function getChatDocuments(accessToken, chatId) {
  return authedGet(`/api/chat/sessions/${chatId}/documents`, accessToken);
}

/**
 * PUT /api/chat/sessions/<id>/documents — replace the document selection.
 * Pass an empty array to clear the selection (use all documents).
 * @param {string} accessToken
 * @param {string} chatId
 * @param {string[]} documentIds
 */
export function setChatDocuments(accessToken, chatId, documentIds) {
  return request(`/api/chat/sessions/${chatId}/documents`, {
    method: "PUT",
    token: accessToken,
    payload: { document_ids: documentIds },
  });
}
