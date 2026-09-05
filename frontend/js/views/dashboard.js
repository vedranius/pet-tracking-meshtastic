import { api } from "../api.js";
import { state, subscribe, trackerById } from "../state.js";
import { onWSMessage } from "../ws.js";
import { timeAgo, parseApiDate } from "../util.js";
import { toast } from "../toast.js";
import { t, onLocaleChange } from "../i18n.js";

const DEFAULT_CENTER = [45.1, 15.2];

export async function mountDashboard(container) {
  container.innerHTML = `
    <div class="dashboard">
      <div id="map"></div>
      <div class="tracker-panel" id="tracker-panel"></div>
    </div>
  `;

  const map = L.map("map", { zoomControl: false }).setView(DEFAULT_CENTER, 7);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);

  const LocateControl = L.Control.extend({
    options: { position: "topright" },
    onAdd() {
      const btn = L.DomUtil.create("button", "locate-btn");
      btn.type = "button";
      btn.innerHTML = "📍";
      btn.title = t("dashboard.locate_me");
      L.DomEvent.disableClickPropagation(btn);
      L.DomEvent.on(btn, "click", locateMe);
      return btn;
    },
  });
  map.addControl(new LocateControl());

  let meMarker = null;
  let meCircle = null;
  function locateMe() {
    if (!navigator.geolocation) {
      toast(t("dashboard.locate_unsupported"), "error");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude, accuracy } = pos.coords;
        if (meMarker) map.removeLayer(meMarker);
        if (meCircle) map.removeLayer(meCircle);
        meMarker = L.marker([latitude, longitude], {
          icon: L.divIcon({
            className: "", html: `<div class="marker-label" style="border-color:#3363c9">🧑</div>`,
            iconSize: [30, 30], iconAnchor: [15, 15],
          }),
        }).addTo(map);
        meCircle = L.circle([latitude, longitude], { radius: accuracy, color: "#3363c9", fillOpacity: 0.08 }).addTo(map);
        map.flyTo([latitude, longitude], 16);
      },
      (err) => {
        // Geolocation is only available in a "secure context" (HTTPS, or
        // localhost) — a self-hosted server reached over a plain LAN IP
        // (the common case here) won't get it from the browser at all,
        // which is worth telling the user rather than a generic failure.
        const insecure = location.protocol !== "https:" && !["localhost", "127.0.0.1"].includes(location.hostname);
        let msg = t("dashboard.locate_failed");
        if (insecure) msg = t("dashboard.locate_insecure");
        else if (err.code === err.PERMISSION_DENIED) msg = t("dashboard.locate_denied");
        toast(msg, "error");
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  const markers = new Map(); // tracker_id -> L.Marker
  const fenceLayer = L.layerGroup().addTo(map);
  let timelineLayer = null;

  function markerIcon(tracker) {
    return L.divIcon({
      className: "",
      html: `<div class="marker-label" style="border-color:${tracker.color}">🐾</div>`,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -17],
    });
  }

  function popupHtml(tracker) {
    const batt = tracker.last_battery != null ? `${tracker.last_battery}%` : "–";
    const speed = tracker.last_speed != null ? `${(tracker.last_speed).toFixed(1)} m/s` : "–";
    return `
      <div>
        <b>${escapeHtml(tracker.name)}</b><br>
        🔋 ${batt} &nbsp; 🏃 ${speed}<br>
        <span class="muted">${t("dashboard.last_fix")}: ${timeAgo(tracker.last_position_at)}</span>
        <div class="popup-ring-btn">
          <button class="btn btn-sm btn-primary" data-ring="${tracker.id}">🔔 ${t("dashboard.ring")}</button>
          <button class="btn btn-sm" data-timeline="${tracker.id}">📈 ${t("dashboard.timeline")}</button>
        </div>
      </div>
    `;
  }

  function upsertMarker(tracker) {
    if (tracker.last_lat == null || tracker.last_lon == null) return;
    const pos = [tracker.last_lat, tracker.last_lon];
    let marker = markers.get(tracker.id);
    if (!marker) {
      marker = L.marker(pos, { icon: markerIcon(tracker) }).addTo(map);
      marker.bindPopup("", { closeButton: true });
      marker.on("popupopen", () => {
        marker.setPopupContent(popupHtml(trackerById(tracker.id) || tracker));
        wirePopupButtons();
      });
      markers.set(tracker.id, marker);
    } else {
      marker.setLatLng(pos);
      marker.setIcon(markerIcon(tracker));
      if (marker.isPopupOpen()) marker.setPopupContent(popupHtml(tracker));
    }
  }

  function wirePopupButtons() {
    document.querySelectorAll("[data-ring]").forEach((btn) => {
      btn.onclick = () => ringTracker(Number(btn.dataset.ring));
    });
    document.querySelectorAll("[data-timeline]").forEach((btn) => {
      btn.onclick = () => openTimeline(Number(btn.dataset.timeline));
    });
  }

  async function ringTracker(trackerId) {
    try {
      await api.post(`/api/trackers/${trackerId}/ring`, {});
      toast(`🔔 ${t("dashboard.ring_sent")}`, "success");
    } catch (e) {
      toast(e.message, "error");
    }
  }

  function drawFences(geofences) {
    fenceLayer.clearLayers();
    for (const f of geofences) {
      if (!f.enabled) continue;
      let geom;
      try { geom = JSON.parse(f.geometry_json); } catch { continue; }
      const t = trackerById(f.tracker_id);
      const color = t ? t.color : "#1f6b4d";
      if (f.shape === "circle") {
        L.circle([geom.lat, geom.lon], { radius: geom.radius_m, color, weight: 2, fillOpacity: 0.08 })
          .bindTooltip(f.name)
          .addTo(fenceLayer);
      } else if (f.shape === "polygon") {
        L.polygon(geom.points, { color, weight: 2, fillOpacity: 0.08 })
          .bindTooltip(f.name)
          .addTo(fenceLayer);
      }
    }
  }

  function renderPanel() {
    const panel = document.getElementById("tracker-panel");
    if (!panel) return;
    if (state.trackers.length === 0) {
      panel.innerHTML = `<div class="list-empty">${t("dashboard.no_trackers")}<br>${t("dashboard.no_trackers_hint")}</div>`;
      return;
    }
    panel.innerHTML = state.trackers.map((t) => `
      <div class="tracker-chip" data-fly="${t.id}">
        <span class="tracker-dot" style="background:${t.color}"></span>
        <div class="tracker-info">
          <div class="tracker-name">${escapeHtml(t.name)}</div>
          <div class="tracker-meta">${t.last_battery != null ? `🔋 ${t.last_battery}% · ` : ""}${timeAgo(t.last_position_at)}</div>
        </div>
        <button class="btn btn-sm" data-ring-chip="${t.id}" title="${t.name}">🔔</button>
      </div>
    `).join("");
    panel.querySelectorAll("[data-fly]").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest("[data-ring-chip]")) return;
        const tr = trackerById(Number(row.dataset.fly));
        if (tr && tr.last_lat != null) {
          map.flyTo([tr.last_lat, tr.last_lon], 17);
          markers.get(tr.id)?.openPopup();
        } else {
          toast(t("dashboard.no_position_yet"), "error");
        }
      });
    });
    panel.querySelectorAll("[data-ring-chip]").forEach((btn) => {
      btn.addEventListener("click", () => ringTracker(Number(btn.dataset.ringChip)));
    });
  }

  async function refreshFences() {
    try {
      const fences = await api.get("/api/geofences");
      drawFences(fences);
    } catch { /* ignore */ }
  }

  function syncMarkers() {
    for (const tr of state.trackers) upsertMarker(tr);
    renderPanel();
  }

  let openTimelineTrackerId = null;
  async function openTimeline(trackerId) {
    openTimelineTrackerId = trackerId;
    const tracker = trackerById(trackerId);
    if (!tracker) return;
    if (timelineLayer) { map.removeLayer(timelineLayer); timelineLayer = null; }

    let bar = document.getElementById("timeline-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "timeline-bar";
      bar.className = "card";
      bar.style.position = "absolute";
      bar.style.left = "10px";
      bar.style.right = "10px";
      bar.style.top = "10px";
      bar.style.zIndex = "1000";
      bar.style.maxHeight = "82vh";
      bar.style.overflowY = "auto";
      container.querySelector(".dashboard").appendChild(bar);
    }
    bar.innerHTML = `
      <div class="card-row">
        <b>📈 ${t("dashboard.timeline")} — ${escapeHtml(tracker.name)}</b>
        <button class="btn btn-sm" id="timeline-close">✕</button>
      </div>
      <select id="timeline-range">
        <option value="1">${t("dashboard.range_1h")}</option>
        <option value="6">${t("dashboard.range_6h")}</option>
        <option value="24" selected>${t("dashboard.range_24h")}</option>
        <option value="168">${t("dashboard.range_7d")}</option>
      </select>
      <div class="timeline-bar">
        <input type="range" id="timeline-slider" min="0" max="0" value="0" disabled>
      </div>
      <div id="timeline-label" class="muted" style="font-size:12px;text-align:center">${t("dashboard.no_data")}</div>
      <div id="timeline-history" class="position-history"></div>
    `;
    document.getElementById("timeline-close").onclick = () => {
      bar.remove();
      if (timelineLayer) { map.removeLayer(timelineLayer); timelineLayer = null; }
      openTimelineTrackerId = null;
    };
    const rangeSelect = document.getElementById("timeline-range");
    rangeSelect.onchange = () => loadTimeline(trackerId, Number(rangeSelect.value));
    await loadTimeline(trackerId, 24);
  }

  let timelineGhost = null;
  async function loadTimeline(trackerId, hours) {
    const positions = await api.get(`/api/trackers/${trackerId}/positions?hours=${hours}`);
    if (timelineLayer) { map.removeLayer(timelineLayer); timelineLayer = null; }
    const slider = document.getElementById("timeline-slider");
    const label = document.getElementById("timeline-label");
    const historyEl = document.getElementById("timeline-history");
    if (!positions.length) {
      slider.disabled = true;
      slider.max = 0;
      label.textContent = t("dashboard.no_data_range");
      historyEl.innerHTML = "";
      return;
    }
    const latlngs = positions.map((p) => [p.lat, p.lon]);
    timelineLayer = L.layerGroup().addTo(map);
    L.polyline(latlngs, { color: "#3363c9", weight: 3, opacity: 0.7 }).addTo(timelineLayer);
    timelineGhost = L.circleMarker(latlngs[latlngs.length - 1], {
      radius: 8, color: "#3363c9", fillColor: "#3363c9", fillOpacity: 1,
    }).addTo(timelineLayer);
    map.fitBounds(latlngs, { maxZoom: 17, padding: [30, 30] });

    slider.disabled = false;
    slider.max = String(positions.length - 1);
    slider.value = String(positions.length - 1);
    const fmt = (p) => parseApiDate(p.ts).toLocaleString();
    const updateLabel = (idx) => {
      const p = positions[idx];
      timelineGhost.setLatLng([p.lat, p.lon]);
      label.textContent = `${fmt(p)}${p.speed != null ? ` · ${p.speed.toFixed(1)} m/s` : ""}`;
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
    updateLabel(positions.length - 1);
  }

  const unsubState = subscribe(() => { syncMarkers(); refreshFences(); });
  const unsubLocale = onLocaleChange(() => { renderPanel(); });
  const unsubWS = onWSMessage((msg) => {
    if (msg.type === "position") {
      const tr = trackerById(msg.tracker_id);
      if (tr) { tr.last_lat = msg.lat; tr.last_lon = msg.lon; tr.last_speed = msg.speed; tr.last_position_at = msg.ts; }
      if (tr) upsertMarker(tr);
      renderPanel();
    } else if (msg.type === "telemetry") {
      const tr = trackerById(msg.tracker_id);
      if (tr) { tr.last_battery = msg.battery_level; }
      renderPanel();
    }
  });

  syncMarkers();
  await refreshFences();
  if (state.trackers.some((t) => t.last_lat != null)) {
    const pts = state.trackers.filter((t) => t.last_lat != null).map((t) => [t.last_lat, t.last_lon]);
    map.fitBounds(pts, { maxZoom: 16, padding: [40, 40] });
  }

  return () => {
    unsubState();
    unsubLocale();
    unsubWS();
    map.remove();
  };
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
