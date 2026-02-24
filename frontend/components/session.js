const SESSION_KEY = "tutorbot.session.v1";

export function getSession() {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw);
  } catch (_) {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function setSessionFromAuth(authPayload) {
  const session = {
    accessToken: authPayload.access_token,
    refreshToken: authPayload.refresh_token,
    user: authPayload.user,
  };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

export function getAccessToken() {
  const session = getSession();
  return session?.accessToken || null;
}
