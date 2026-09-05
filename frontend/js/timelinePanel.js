import { parseApiDate } from "./util.js";
import { t } from "./i18n.js";

/** Shared "movement history" floating panel used by both the pet timeline
 * on the dashboard and the admin dashboard's per-user/per-pet timelines.
 * Draws a path + scrubber + per-fix list on `map`, sourced from whatever
 * `fetchPositions({hours} | {date})` returns — the caller decides which
 * API endpoint that hits (own tracker, admin-viewed tracker, or a user's
 * phone location history), this just handles the range/day picking and
 * rendering, which is otherwise identical in every case.
 *
 * The per-fix list is collapsed by default (a native <details> element) —
 * it used to be always open and, especially over a map as short as the
 * admin dashboard's, could grow tall enough to cover the map it's supposed
 * to be annotating. The controls strip above it stays compact so the path
 * itself is visible immediately. */
export function openTimelinePanel({ container, map, title, color = "#3363c9", fetchPositions, onCloseExtra }) {
  let layer = null;
  let ghost = null;
  let currentPositions = [];

  const today = new Date();
  const maxDate = today.toISOString().slice(0, 10);
  const minDateObj = new Date(today.getTime() - 13 * 24 * 60 * 60 * 1000);
  const minDate = minDateObj.toISOString().slice(0, 10);

  let bar = document.createElement("div");
  bar.className = "card timeline-panel-bar";
  container.appendChild(bar);

  bar.innerHTML = `
    <div class="card-row">
      <b>📈 ${escapeHtml(title)}</b>
      <button class="btn btn-sm" data-close>✕</button>
    </div>
    <div class="timeline-controls">
      <select id="tp-range">
        <option value="1">${t("dashboard.range_1h")}</option>
        <option value="6">${t("dashboard.range_6h")}</option>
        <option value="24" selected>${t("dashboard.range_24h")}</option>
        <option value="72">${t("dashboard.range_3d")}</option>
        <option value="168">${t("dashboard.range_7d")}</option>
        <option value="336">${t("dashboard.range_14d")}</option>
      </select>
      <span class="muted" style="font-size:12px">${t("dashboard.or_pick_day")}</span>
      <input type="date" id="tp-date" min="${minDate}" max="${maxDate}">
      <button class="btn btn-sm" id="tp-clear-date" hidden>${t("dashboard.back_to_range")}</button>
    </div>
    <div class="timeline-bar">
      <button class="btn btn-sm" id="tp-prev" disabled title="${t("dashboard.step_prev")}">⏮</button>
      <input type="range" id="tp-slider" min="0" max="0" value="0" disabled>
      <button class="btn btn-sm" id="tp-next" disabled title="${t("dashboard.step_next")}">⏭</button>
    </div>
    <div id="tp-label" class="muted" style="font-size:12px;text-align:center">${t("dashboard.no_data")}</div>
    <details id="tp-details">
      <summary id="tp-summary">${t("dashboard.show_list")}</summary>
      <div id="tp-history" class="position-history"></div>
    </details>
  `;

  const rangeSelect = bar.querySelector("#tp-range");
  const dateInput = bar.querySelector("#tp-date");
  const clearDateBtn = bar.querySelector("#tp-clear-date");
  const slider = bar.querySelector("#tp-slider");
  const prevBtn = bar.querySelector("#tp-prev");
  const nextBtn = bar.querySelector("#tp-next");
  const label = bar.querySelector("#tp-label");
  const summary = bar.querySelector("#tp-summary");
  const historyEl = bar.querySelector("#tp-history");

  function close() {
    bar.remove();
    if (layer) { map.removeLayer(layer); layer = null; }
    onCloseExtra?.();
  }
  bar.querySelector("[data-close]").addEventListener("click", close);

  rangeSelect.addEventListener("change", () => {
    dateInput.value = "";
    clearDateBtn.hidden = true;
    load({ hours: Number(rangeSelect.value) });
  });
  dateInput.addEventListener("change", () => {
    if (!dateInput.value) return;
    clearDateBtn.hidden = false;
    load({ date: dateInput.value });
  });
  clearDateBtn.addEventListener("click", () => {
    dateInput.value = "";
    clearDateBtn.hidden = true;
    load({ hours: Number(rangeSelect.value) });
  });

  async function load(params) {
    let positions = [];
    try {
      positions = await fetchPositions(params);
    } catch { /* show as "no data" below rather than an uncaught error */ }
    currentPositions = positions;

    if (layer) { map.removeLayer(layer); layer = null; }
    if (!positions.length) {
      slider.disabled = true;
      slider.max = 0;
      prevBtn.disabled = true;
      nextBtn.disabled = true;
      label.textContent = t("dashboard.no_data_range");
      summary.textContent = t("dashboard.show_list");
      historyEl.innerHTML = "";
      return;
    }

    const latlngs = positions.map((p) => [p.lat, p.lon]);
    layer = L.layerGroup().addTo(map);
    // The connecting line plus a small dot at every fix (not just the
    // scrubbed "ghost" position) makes the step-by-step path itself legible
    // at a glance, before ever touching the slider.
    L.polyline(latlngs, { color, weight: 3, opacity: 0.6 }).addTo(layer);
    for (const ll of latlngs) {
      L.circleMarker(ll, { radius: 3, color, fillColor: color, fillOpacity: 0.9, weight: 1 }).addTo(layer);
    }
    ghost = L.circleMarker(latlngs[latlngs.length - 1], { radius: 8, color, fillColor: color, fillOpacity: 1 }).addTo(layer);
    map.fitBounds(latlngs, { maxZoom: 17, padding: [30, 30] });

    slider.disabled = false;
    slider.max = String(positions.length - 1);
    slider.value = String(positions.length - 1);
    prevBtn.disabled = false;
    nextBtn.disabled = false;
    summary.textContent = t("dashboard.show_list_count", { n: positions.length });
    const fmt = (p) => parseApiDate(p.ts).toLocaleString();
    const updateLabel = (idx) => {
      const p = positions[idx];
      ghost.setLatLng([p.lat, p.lon]);
      label.textContent = `${fmt(p)}${p.speed != null ? ` · ${p.speed.toFixed(1)} m/s` : ""}${p.battery != null ? ` · 🔋 ${p.battery}%` : ""}`;
      historyEl.querySelectorAll(".position-row").forEach((row) => {
        row.classList.toggle("active", Number(row.dataset.idx) === idx);
      });
    };

    // most recent first, so the newest fix is always at the top of the list
    historyEl.innerHTML = positions.map((p, idx) => `
      <div class="position-row" data-idx="${idx}">
        <div>
          <div class="position-time">${fmt(p)}</div>
          <div class="position-coords">${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}${p.speed != null ? ` · ${p.speed.toFixed(1)} m/s` : ""}</div>
        </div>
        <a class="position-maps" href="https://maps.google.com/?q=${p.lat},${p.lon}" target="_blank" rel="noopener" title="${t("dashboard.open_in_maps")}">🗺️</a>
      </div>
    `).reverse().join("");
    historyEl.querySelectorAll(".position-row").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".position-maps")) return;
        const idx = Number(row.dataset.idx);
        slider.value = String(idx);
        updateLabel(idx);
      });
    });

    slider.oninput = () => updateLabel(Number(slider.value));
    prevBtn.onclick = () => {
      const idx = Math.max(0, Number(slider.value) - 1);
      slider.value = String(idx);
      updateLabel(idx);
    };
    nextBtn.onclick = () => {
      const idx = Math.min(currentPositions.length - 1, Number(slider.value) + 1);
      slider.value = String(idx);
      updateLabel(idx);
    };
    updateLabel(positions.length - 1);
  }

  load({ hours: 24 });
  return { close };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
