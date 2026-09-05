import { api } from "../api.js";
import { onWSMessage } from "../ws.js";
import { fmtDateTime } from "../util.js";
import { t, onLocaleChange } from "../i18n.js";
import { renderEventText } from "../eventText.js";

const ICONS = {
  geofence_exit: "🚨",
  geofence_exit_update: "📍",
  geofence_enter: "✅",
  low_battery: "🔋",
  offline: "📴",
  ring_sent: "🔔",
};

export async function mountAlerts(container) {
  container.innerHTML = `
    <div class="page">
      <div class="page-header"><h2>🔔 ${t("nav.alerts")}</h2></div>
      <div class="card" id="events-card"><div id="events-list"></div></div>
    </div>
  `;

  let events = [];

  function render() {
    const listEl = document.getElementById("events-list");
    if (!events.length) {
      listEl.innerHTML = `<div class="list-empty">${t("alerts.none")}</div>`;
      return;
    }
    listEl.innerHTML = events.map((e) => `
      <div class="event-row">
        <div class="event-icon">${ICONS[e.type] || "•"}</div>
        <div>
          <div class="event-msg">${escapeHtml(renderEventText(e.type, e.message))}</div>
          <div class="event-time">${fmtDateTime(e.ts)}</div>
        </div>
      </div>
    `).join("");
  }

  async function load() {
    events = await api.get("/api/events?limit=200");
    render();
  }

  const unsubWs = onWSMessage((msg) => {
    if (msg.type === "alert") load();
  });
  const unsubLocale = onLocaleChange(render);

  await load();
  return () => { unsubWs(); unsubLocale(); };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
