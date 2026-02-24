import { APIError, login, register } from "../../components/api_client.js";
import { getSession, setSessionFromAuth } from "../../components/session.js";

const form = document.querySelector("[data-auth-form]");
const mode = form?.dataset.mode;
const messageEl = document.querySelector("[data-form-message]");
const submitButton = document.querySelector("[data-submit-btn]");
const defaultButtonText = submitButton?.textContent || "Submit";

if (!form || !mode) {
  throw new Error("auth form is missing required attributes");
}

if (getSession()?.accessToken) {
  window.location.replace("../index.html");
}

function setMessage(message, type = "error") {
  messageEl.textContent = message || "";
  messageEl.classList.remove("error", "success");
  if (message) {
    messageEl.classList.add(type);
  }
}

function setLoading(isLoading) {
  submitButton.disabled = isLoading;
  if (isLoading) {
    submitButton.textContent = mode === "signup" ? "Creating..." : "Signing In...";
  } else {
    submitButton.textContent = defaultButtonText;
  }
}

function validateInput() {
  const email = form.email.value.trim().toLowerCase();
  const password = form.password.value;

  if (!email || !password) {
    return { ok: false, message: "Email and password are required." };
  }

  if (mode === "signup") {
    const confirmPassword = form.confirm_password.value;
    if (password.length < 8) {
      return { ok: false, message: "Password must be at least 8 characters." };
    }
    if (password !== confirmPassword) {
      return { ok: false, message: "Passwords do not match." };
    }
  }

  return { ok: true };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  setMessage("");

  const validation = validateInput();
  if (!validation.ok) {
    setMessage(validation.message, "error");
    return;
  }

  const email = form.email.value.trim().toLowerCase();
  const password = form.password.value;
  const username = form.username ? form.username.value.trim() : "";

  setLoading(true);
  try {
    const payload =
      mode === "signup"
        ? await register(email, password, username || null)
        : await login(email, password);

    setSessionFromAuth(payload);
    setMessage("Success. Redirecting...", "success");
    window.setTimeout(() => {
      window.location.replace("../index.html");
    }, 420);
  } catch (error) {
    if (error instanceof APIError) {
      setMessage(error.message, "error");
    } else {
      setMessage("Unexpected error occurred. Please try again.", "error");
    }
  } finally {
    setLoading(false);
  }
});
