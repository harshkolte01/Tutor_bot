import { APIError, getAiStatus } from "../../components/api_client.js";

const CONNECTED_SESSION_KEY = "tutorbot.aiAgentConnected.v1";
const statusEl = document.querySelector("[data-ai-status]");
const labelEl = document.querySelector("[data-ai-status-label]");

if (statusEl && labelEl) {
  if (sessionStorage.getItem(CONNECTED_SESSION_KEY) === "1") {
    setState("connected", "AI agent connected");
  } else {
    setState("connecting", "Connecting to AI agent");
    checkAiStatus();
  }
}

async function checkAiStatus() {
  try {
    const status = await getAiStatus();
    if (status?.ok) {
      sessionStorage.setItem(CONNECTED_SESSION_KEY, "1");
      setState("connected", "AI agent connected");
      return;
    }

    const message =
      status?.status === "not_configured"
        ? "AI agent not configured"
        : "Connecting to AI agent";
    setState(status?.status || "connecting", message);
    scheduleRetry(status?.retry_after_sec);
  } catch (error) {
    const message =
      error instanceof APIError && error.statusCode === 0
        ? "Backend connection unavailable"
        : "Connecting to AI agent";
    setState("connecting", message);
    scheduleRetry(10);
  }
}

function setState(state, label) {
  statusEl.hidden = false;
  statusEl.dataset.aiState = state;
  statusEl.title = label;
  statusEl.setAttribute("aria-label", label);
  labelEl.textContent = label;
}

function scheduleRetry(seconds) {
  const retryMs = Math.max(5, Number(seconds) || 10) * 1000;
  window.setTimeout(checkAiStatus, retryMs);
}
