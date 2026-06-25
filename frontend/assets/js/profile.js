import { APIError, changePassword, getMe } from "../../components/api_client.js";
import {
  clearSession,
  getSession,
  updateSessionUser,
} from "../../components/session.js";

const session = getSession();
if (!session?.accessToken) {
  window.location.replace("./login.html");
  throw new Error("unauthenticated");
}

const avatarEl = document.querySelector("[data-user-slot]");
const profileAvatarEl = document.querySelector("[data-profile-avatar]");
const displayNameEl = document.querySelector("[data-profile-display-name]");
const profileEmailEl = document.querySelector("[data-profile-email]");
const usernameEl = document.querySelector("[data-profile-username]");
const emailDetailEl = document.querySelector("[data-profile-email-detail]");
const profileStatusEl = document.getElementById("profile-status");
const passwordForm = document.getElementById("password-form");
const currentPasswordInput = document.getElementById("current-password");
const newPasswordInput = document.getElementById("new-password");
const passwordSubmit = document.getElementById("password-submit");
const passwordStatusEl = document.getElementById("password-status");

function getToken() {
  return getSession()?.accessToken || null;
}

function getDisplayName(user) {
  return user?.username || user?.email || "User";
}

function renderUser(user) {
  const displayName = getDisplayName(user);
  const initial = displayName.charAt(0).toUpperCase();
  const username = user?.username || "Not set";
  const email = user?.email || "Not available";

  if (avatarEl) {
    avatarEl.textContent = initial;
    avatarEl.title = displayName;
  }
  if (profileAvatarEl) {
    profileAvatarEl.textContent = initial;
  }
  displayNameEl.textContent = displayName;
  profileEmailEl.textContent = email;
  usernameEl.textContent = username;
  emailDetailEl.textContent = email;
}

function setProfileStatus(message, type = "") {
  profileStatusEl.textContent = message;
  profileStatusEl.className = "status-line" + (type ? ` ${type}` : "");
}

function setPasswordStatus(message, type = "") {
  passwordStatusEl.textContent = message;
  passwordStatusEl.className = "status-line" + (type ? ` ${type}` : "");
}

function setPasswordLoading(isLoading) {
  passwordSubmit.disabled = isLoading;
  passwordSubmit.textContent = isLoading ? "Updating..." : "Update Password";
}

document.querySelector("[data-signout]").addEventListener("click", () => {
  clearSession();
  window.location.replace("./login.html");
});

renderUser(session.user);
loadProfile();

passwordForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setPasswordStatus("");

  const currentPassword = currentPasswordInput.value;
  const newPassword = newPasswordInput.value;

  if (!currentPassword || !newPassword) {
    setPasswordStatus("Old password and new password are required.", "err");
    return;
  }
  if (newPassword.length < 8) {
    setPasswordStatus("New password must be at least 8 characters.", "err");
    newPasswordInput.focus();
    return;
  }
  if (currentPassword === newPassword) {
    setPasswordStatus("New password must be different from old password.", "err");
    newPasswordInput.focus();
    return;
  }

  setPasswordLoading(true);
  setPasswordStatus("Updating password...");

  try {
    await changePassword(getToken(), currentPassword, newPassword);
    passwordForm.reset();
    setPasswordStatus("Password updated.", "ok");
  } catch (error) {
    setPasswordStatus(
      error instanceof APIError ? error.message : "Failed to update password.",
      "err",
    );
  } finally {
    setPasswordLoading(false);
  }
});

async function loadProfile() {
  setProfileStatus("Loading profile...");
  try {
    const response = await getMe(getToken());
    if (response?.user) {
      updateSessionUser(response.user);
      renderUser(response.user);
    }
    setProfileStatus("");
  } catch (error) {
    setProfileStatus(
      error instanceof APIError ? error.message : "Could not refresh profile.",
      "err",
    );
  }
}
