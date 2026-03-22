import {
  APIError,
  getAnalyticsOverview,
  getAnalyticsProgress,
  getAnalyticsWeakTopics,
} from "../../components/api_client.js";
import { clearSession, getSession } from "../../components/session.js";

const EVENT_META = [
  { key: "doc_uploaded", label: "Doc Uploads", color: "#0f766e" },
  { key: "doc_text_added", label: "Text Notes", color: "#14b8a6" },
  { key: "chat_asked", label: "Chat Questions", color: "#2563eb" },
  { key: "quiz_created", label: "Quizzes Created", color: "#f59e0b" },
  { key: "quiz_submitted", label: "Quizzes Submitted", color: "#a855f7" },
];

const session = getSession();
if (!session?.accessToken) {
  window.location.replace("./login.html");
  throw new Error("unauthenticated");
}

const { user } = session;

function getToken() {
  return getSession()?.accessToken || null;
}

const displayName = user?.username || user?.email || "";
const avatarEl = document.querySelector("[data-user-slot]");
if (avatarEl) {
  avatarEl.textContent = displayName.charAt(0).toUpperCase();
  avatarEl.title = displayName;
}

document.querySelector("[data-signout]").addEventListener("click", () => {
  clearSession();
  window.location.replace("./login.html");
});

const refreshBtn = document.getElementById("refresh-analytics-btn");
const statusEl = document.getElementById("analytics-status");
const overviewGrid = document.getElementById("overview-grid");
const eventChipList = document.getElementById("event-chip-list");
const activityMixCaption = document.getElementById("activity-mix-caption");
const summaryStrip = document.getElementById("summary-strip");
const progressSummaryCaption = document.getElementById("progress-summary-caption");
const activityChart = document.getElementById("activity-chart");
const scoreList = document.getElementById("score-list");
const scoreTrendCaption = document.getElementById("score-trend-caption");
const weakTopicList = document.getElementById("weak-topic-list");
const weakTopicsCaption = document.getElementById("weak-topics-caption");

refreshBtn.addEventListener("click", () => {
  loadAnalytics();
});

loadAnalytics();

async function loadAnalytics() {
  refreshBtn.disabled = true;
  setStatus("Loading analytics...");

  try {
    const [overview, progress, weakTopicPayload] = await Promise.all([
      getAnalyticsOverview(getToken()),
      getAnalyticsProgress(getToken()),
      getAnalyticsWeakTopics(getToken()),
    ]);

    renderOverview(overview || {});
    renderProgress(progress || {});
    renderWeakTopics(weakTopicPayload || {});
    setStatus(`Updated ${formatDateTime(new Date().toISOString())}`, "ok");
  } catch (error) {
    const message =
      error instanceof APIError ? error.message : "Failed to load analytics.";
    renderErrorState(message);
    setStatus(message, "err");
  } finally {
    refreshBtn.disabled = false;
  }
}

function renderOverview(overview) {
  const totals = overview?.totals || {};
  const eventCounts = overview?.event_counts || {};
  const totalEvents = EVENT_META.reduce(
    (sum, meta) => sum + Number(eventCounts?.[meta.key] || 0),
    0,
  );

  overviewGrid.innerHTML = [
    renderMetricCard(
      "Documents",
      formatNumber(totals.documents),
      `${formatNumber(totals.uploaded_documents)} uploads • ${formatNumber(totals.text_documents)} text notes`,
    ),
    renderMetricCard(
      "Chat Sessions",
      formatNumber(totals.chat_sessions),
      "All saved study conversations",
    ),
    renderMetricCard(
      "Quizzes",
      formatNumber(totals.quizzes),
      "Generated quizzes in your workspace",
    ),
    renderMetricCard(
      "Submitted Attempts",
      formatNumber(totals.submitted_attempts),
      "Attempts included in your trend data",
    ),
    renderMetricCard(
      "Average Score",
      formatPercent(overview?.average_score_percent),
      "Across submitted quiz attempts",
    ),
    renderMetricCard(
      "Tracked Events",
      formatNumber(totalEvents),
      overview?.latest_activity_at
        ? `Latest activity ${formatDateTime(overview.latest_activity_at)}`
        : "No tracked activity yet",
    ),
  ].join("");

  eventChipList.innerHTML = EVENT_META.map((meta) => `
    <span class="event-chip">
      <span class="event-chip-dot" style="background:${meta.color};"></span>
      <span>${escHtml(meta.label)}: <strong>${formatNumber(eventCounts?.[meta.key])}</strong></span>
    </span>
  `).join("");

  activityMixCaption.textContent = `${pluralize(totalEvents, "tracked event")} recorded so far.`;
}

function renderProgress(progress) {
  const summary = progress?.summary || {};
  const dailyActivity = Array.isArray(progress?.daily_activity)
    ? progress.daily_activity
    : [];
  const scoreTrend = Array.isArray(progress?.quiz_score_trend)
    ? progress.quiz_score_trend
    : [];

  summaryStrip.innerHTML = [
    renderSummaryPill(formatNumber(summary.days), "Days in view"),
    renderSummaryPill(formatNumber(summary.active_days), "Active days"),
    renderSummaryPill(formatNumber(summary.total_events), "Events in window"),
    renderSummaryPill(formatPercent(summary.average_score_percent), "Average score"),
  ].join("");

  progressSummaryCaption.textContent = `Last ${formatNumber(summary.days)} days • ${pluralize(summary.submitted_attempts || 0, "submitted attempt")}.`;

  if (!dailyActivity.length) {
    activityChart.innerHTML = '<div class="empty-analytics" style="grid-column:1 / -1;">No activity data available yet.</div>';
  } else {
    const maxTotal = Math.max(
      ...dailyActivity.map((day) => Number(day.total || 0)),
      1,
    );
    activityChart.innerHTML = dailyActivity.map((day) => renderActivityDay(day, maxTotal)).join("");
  }

  const scoredDays = scoreTrend.filter((day) => Number(day.attempt_count || 0) > 0);
  scoreTrendCaption.textContent = scoredDays.length
    ? `${pluralize(scoredDays.length, "day")} with submitted quiz data.`
    : "No submitted quiz scores yet.";

  if (!scoredDays.length) {
    scoreList.innerHTML = '<div class="empty-analytics">Submit a quiz to start building your score trend.</div>';
    return;
  }

  scoreList.innerHTML = scoredDays.map((day) => `
    <div class="score-row">
      <div class="score-date">${escHtml(formatShortDate(day.date))}</div>
      <div class="score-bar-shell">
        <div class="score-bar" style="width:${clampPercent(day.average_score_percent)}%;"></div>
      </div>
      <div class="score-meta">${escHtml(formatPercent(day.average_score_percent))} • ${pluralize(day.attempt_count, "attempt")}</div>
    </div>
  `).join("");
}

function renderWeakTopics(payload) {
  const weakTopics = Array.isArray(payload?.weak_topics) ? payload.weak_topics : [];

  weakTopicsCaption.textContent = weakTopics.length
    ? `Showing ${pluralize(weakTopics.length, "topic")} with the lowest recent accuracy.`
    : "No submitted attempts yet.";

  if (!weakTopics.length) {
    weakTopicList.innerHTML = '<div class="empty-analytics">Finish and submit a quiz to see weak-topic insights here.</div>';
    return;
  }

  weakTopicList.innerHTML = weakTopics.map((topic) => `
    <article class="weak-topic-card">
      <div class="weak-topic-head">
        <div>
          <h3>${escHtml(topic.topic || "Untitled Topic")}</h3>
        </div>
        <span class="topic-badge">${escHtml(formatPercent(topic.accuracy_percent))} accuracy</span>
      </div>
      <div class="topic-meta-grid">
        ${renderTopicMeta("Average Score", formatPercent(topic.average_score_percent))}
        ${renderTopicMeta("Attempts", pluralize(topic.attempt_count || 0, "attempt"))}
        ${renderTopicMeta("Question Results", `${formatNumber(topic.correct_count)} correct • ${formatNumber(topic.incorrect_count)} incorrect`)}
        ${renderTopicMeta("Latest Attempt", topic.latest_attempt_at ? formatDateTime(topic.latest_attempt_at) : "No attempt")}
      </div>
    </article>
  `).join("");
}

function renderMetricCard(label, value, note) {
  return `
    <article class="metric-card">
      <span class="metric-card-label">${escHtml(label)}</span>
      <span class="metric-card-value">${escHtml(value)}</span>
      <span class="metric-card-note">${escHtml(note)}</span>
    </article>
  `;
}

function renderSummaryPill(value, label) {
  return `
    <div class="summary-pill">
      <strong>${escHtml(value)}</strong>
      <span>${escHtml(label)}</span>
    </div>
  `;
}

function renderActivityDay(day, maxTotal) {
  const total = Number(day?.total || 0);
  const height = total > 0 ? Math.max(8, (total / maxTotal) * 100) : 0;
  const segments = total > 0
    ? EVENT_META.map((meta) => {
        const count = Number(day?.[meta.key] || 0);
        if (!count) {
          return "";
        }
        return `<div class="activity-segment" style="height:${(count / total) * 100}%;background:${meta.color};" title="${escHtml(meta.label)}: ${count}"></div>`;
      }).join("")
    : "";

  return `
    <div class="activity-day">
      <div class="activity-bar-shell">
        <div class="activity-bar" style="height:${height}%;">
          ${segments}
        </div>
      </div>
      <span class="activity-day-label">${escHtml(formatTinyDate(day.date))}</span>
      <span class="activity-day-total">${formatNumber(total)}</span>
    </div>
  `;
}

function renderTopicMeta(label, value) {
  return `
    <div class="topic-meta">
      <span class="topic-meta-label">${escHtml(label)}</span>
      <span class="topic-meta-value">${escHtml(value)}</span>
    </div>
  `;
}

function renderErrorState(message) {
  const escapedMessage = escHtml(message);
  overviewGrid.innerHTML = `<div class="empty-analytics" style="grid-column:1 / -1;">${escapedMessage}</div>`;
  eventChipList.innerHTML = `<div class="empty-analytics">${escapedMessage}</div>`;
  summaryStrip.innerHTML = `<div class="empty-analytics" style="grid-column:1 / -1;">${escapedMessage}</div>`;
  activityChart.innerHTML = `<div class="empty-analytics" style="grid-column:1 / -1;">${escapedMessage}</div>`;
  scoreList.innerHTML = `<div class="empty-analytics">${escapedMessage}</div>`;
  weakTopicList.innerHTML = `<div class="empty-analytics">${escapedMessage}</div>`;
  activityMixCaption.textContent = "Unable to load analytics.";
  progressSummaryCaption.textContent = "Unable to load analytics.";
  scoreTrendCaption.textContent = "Unable to load analytics.";
  weakTopicsCaption.textContent = "Unable to load analytics.";
}

function setStatus(message, type = "") {
  statusEl.textContent = message;
  statusEl.className = "status-line" + (type ? ` ${type}` : "");
}

function formatNumber(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) {
    return "0";
  }
  return new Intl.NumberFormat().format(numeric);
}

function formatPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "No data";
  }
  return `${Math.round(numeric)}%`;
}

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.max(0, Math.min(100, numeric));
}

function formatDateTime(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatShortDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

function formatTinyDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

function pluralize(count, word) {
  const numeric = Number(count || 0);
  return `${formatNumber(numeric)} ${word}${numeric === 1 ? "" : "s"}`;
}

function escHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
