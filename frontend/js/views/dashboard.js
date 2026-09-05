import { api } from "../api.js";
import { state, subscribe, trackerById } from "../state.js";
import { onWSMessage } from "../ws.js";
import { timeAgo } from "../util.js";
import { toast } from "../toast.js";
import { t, onLocaleChange } from "../i18n.js";
import { openTimelinePanel } from "../timelinePanel.js";

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
  let currentTimeline = null;

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
    // Ring pushes a command to the pet's own radio node — a control action,
    // so it's hidden for pets shared with this account as a caretaker
    // (read-only access, see backend/app/services/access.py).
    const ringBtn = tracker.is_owner !== false
      ? `<button class="btn btn-sm btn-primary" data-ring="${tracker.id}">🔔 ${t("dashboard.ring")}</button>`
      : "";
    return `
      <div>
        <b>${escapeHtml(tracker.name)}</b><br>
        🔋 ${batt} &nbsp; 🏃 ${speed}<br>
        <span class="muted">${t("dashboard.last_fix")}: ${timeAgo(tracker.last_position_at)}</span>
        <div class="popup-ring-btn">
          ${ringBtn}
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
        ${t.is_owner !== false ? `<button class="btn btn-sm" data-ring-chip="${t.id}" title="${t.name}">🔔</button>` : ""}
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

  function openTimeline(trackerId) {
    const tracker = trackerById(trackerId);
    if (!tracker) return;
    currentTimeline?.close();
    currentTimeline = openTimelinePanel({
      container: container.querySelector(".dashboard"),
      map,
      title: `${t("dashboard.timeline")} — ${tracker.name}`,
      color: tracker.color,
      fetchPositions: (params) => {
        const q = params.date ? `date=${params.date}` : `hours=${params.hours}`;
        return api.get(`/api/trackers/${trackerId}/positions?${q}`);
      },
      onCloseExtra: () => { currentTimeline = null; },
    });
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
