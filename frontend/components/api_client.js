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

async function request(
  path,
  {
    method = "GET",
    token = null,
    payload,
    params = null,
    timeoutMs = 10000,
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
